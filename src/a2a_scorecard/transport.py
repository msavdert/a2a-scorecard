"""Per-scan HTTP transport: pacing, 429 handling, and hard budgets.

Implements ADR-0020. There is no shared request helper in this codebase -
each check calls the httpx client directly and interprets the status
itself - so policy enforcement that must see every response (429 handling)
or every request (the budget, the deadline, per-host pacing) goes beneath
the client, in one `httpx.BaseTransport`, rather than into five call
sites. One `ScanTransport` instance is built per scan.
"""

from __future__ import annotations

import datetime
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Any

import httpx


@dataclass(frozen=True)
class ScanLimits:
    """Hard caps enforced by `ScanTransport`, per docs/SCANNING-POLICY.md
    "Volume and pacing". Defaults are the policy's numbers, not tuning
    knobs: loosening them is a policy change (ADR-0020), not a code
    preference."""

    max_requests: int = 9
    deadline_s: float = 90.0
    pace_per_host_s: float = 0.5
    retry_after_default_s: float = 5.0
    retry_after_cap_s: float = 60.0


class HostPacer:
    """Serializes and paces requests keyed by an arbitrary caller-derived
    key (in production, the request's host; see `ScanTransport`).

    Holds a per-key lock across the whole `slot()` body, so two requests
    to the same key can never overlap in time - this is what makes
    per-host serialization true even when a card's declared interface
    points at a host the batch scheduler never grouped. `clock` and
    `sleep` are injectable so the pacing arithmetic (how long to wait
    before the next request to a key is allowed) is unit-testable in zero
    wall-clock time.
    """

    def __init__(
        self,
        pace_s: float,
        *,
        key: Callable[[Any], str] | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._pace_s = pace_s
        self._key = key or (lambda raw: str(raw))
        self._clock = clock
        self._sleep = sleep
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()
        self._next_allowed: dict[str, float] = {}

    def _lock_for(self, key: str) -> threading.Lock:
        with self._locks_guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = threading.Lock()
                self._locks[key] = lock
            return lock

    @contextmanager
    def slot(self, raw_key: Any) -> Iterator[None]:
        """Block until this key has waited at least `pace_s` since the end
        of the last `slot()` for the same key, then hold the key's lock for
        the duration of the `with` body."""
        key = self._key(raw_key)
        lock = self._lock_for(key)
        with lock:
            now = self._clock()
            wait_until = self._next_allowed.get(key, 0.0)
            if wait_until > now:
                self._sleep(wait_until - now)
            try:
                yield
            finally:
                self._next_allowed[key] = self._clock() + self._pace_s


class ScanAborted(Exception):
    """Base for exceptions that abort a scan outright.

    CRITICAL: this must NOT derive from `httpx.HTTPError`. Every check's
    request call is wrapped in `except (httpx.HTTPError, httpx.InvalidURL)`
    to turn a failed request into a scored FAIL result without crashing the
    scan; if an abort were an `httpx.HTTPError`, those handlers would catch
    it too, and a throttled or budget-exhausted scan would silently score
    the current check FAIL instead of aborting the way this whole design
    exists to guarantee. `scan.py` also re-raises `ScanAborted` ahead of its
    own blanket `except Exception` for the same reason.
    """


class Throttled(ScanAborted):
    """A target returned HTTP 429 and the transport is not retrying:
    either the request was not a GET, the Retry-After was over the cap, or
    a GET was retried once and throttled again."""


class RequestBudgetExceeded(ScanAborted):
    """The scan tried to issue more than `ScanLimits.max_requests`
    requests."""


class ScanDeadlineExceeded(ScanAborted):
    """The scan has been running longer than `ScanLimits.deadline_s`."""


def parse_retry_after(value: str | None, *, default_s: float) -> float:
    """Parse a `Retry-After` header value into a delay in seconds.

    Accepts delta-seconds ("120") or an HTTP-date
    (RFC 7231 IMF-fixdate and the formats `email.utils` understands).
    Anything else - missing header, unparseable date, negative delay -
    returns `default_s` rather than raising: a target that sends a
    malformed header should not crash the scanner, and the transport's
    caller (not this function) is responsible for aborting when the
    resulting delay is over the cap.
    """
    if value is None:
        return default_s
    text = value.strip()
    if not text:
        return default_s
    try:
        return float(int(text))
    except ValueError:
        pass
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        return default_s
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.UTC)
    delta = (parsed - datetime.datetime.now(datetime.UTC)).total_seconds()
    if delta < 0:
        return default_s
    return delta


class ScanTransport(httpx.BaseTransport):
    """Wraps an inner `httpx.BaseTransport` (real network I/O by default)
    with the policy's request budget, wall-clock deadline, per-host pacing,
    and 429 handling. One instance per scan.

    Enforcement order per attempt, per ADR-0020: request budget, then
    deadline, then a pacer slot for the request's host, then delegate to
    the inner transport.
    """

    def __init__(
        self,
        inner: httpx.BaseTransport | None = None,
        limits: ScanLimits | None = None,
        *,
        pacer: HostPacer | None = None,
        host_key: Callable[[httpx.URL], str] | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._inner = inner or httpx.HTTPTransport()
        self.limits = limits or ScanLimits()
        self._host_key = host_key or (lambda url: url.host)
        self._clock = clock
        self._sleep = sleep
        self.pacer = pacer or HostPacer(
            self.limits.pace_per_host_s, key=self._host_key, clock=clock, sleep=sleep
        )
        self._started_at = clock()
        self._request_count = 0
        self._count_lock = threading.Lock()

    def _check_budget(self) -> None:
        with self._count_lock:
            if self._request_count >= self.limits.max_requests:
                raise RequestBudgetExceeded(
                    f"scan exceeded its {self.limits.max_requests}-request budget"
                )
            self._request_count += 1

    def _check_deadline(self) -> None:
        elapsed = self._clock() - self._started_at
        if elapsed > self.limits.deadline_s:
            raise ScanDeadlineExceeded(
                f"scan exceeded its {self.limits.deadline_s}s deadline ({elapsed:.1f}s elapsed)"
            )

    def _attempt(self, request: httpx.Request) -> httpx.Response:
        self._check_budget()
        self._check_deadline()
        with self.pacer.slot(request.url):
            return self._inner.handle_request(request)

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        response = self._attempt(request)
        if response.status_code != 429:
            return response

        if request.method.upper() != "GET":
            # Load-bearing rule (ADR-0020): retrying a POST would spend a
            # second SendMessage ping, and the policy bounds a scan to at
            # most two message pings total. A retry policy that quietly
            # doubles the pings is a policy violation implemented as a
            # feature, so any non-GET 429 aborts immediately.
            response.close()
            raise Throttled(
                f"{request.method} {request.url} was throttled (429); "
                "non-GET requests are never retried"
            )

        retry_after = parse_retry_after(
            response.headers.get("Retry-After"), default_s=self.limits.retry_after_default_s
        )
        response.close()
        if retry_after > self.limits.retry_after_cap_s:
            raise Throttled(
                f"GET {request.url} was throttled (429) with Retry-After={retry_after}s, "
                f"over the {self.limits.retry_after_cap_s}s cap; aborting without retry"
            )

        self._sleep(retry_after)
        response = self._attempt(request)
        if response.status_code == 429:
            response.close()
            raise Throttled(f"GET {request.url} was throttled again after one retry; aborting")
        return response

    def close(self) -> None:
        self._inner.close()
