"""Unit and fake-agent tests for `a2a_scorecard.transport` (ADR-0020).

Pacing arithmetic and the header parser are tested with an injected clock
and a recording sleep so they run in zero wall-clock time. The throttle-mode
tests talk to the in-process fake agent (CLAUDE.md rule: tests never touch
the network).
"""

from __future__ import annotations

import datetime
from email.utils import format_datetime

import httpx
import pytest

from a2a_scorecard.config import Settings
from a2a_scorecard.models import CheckStatus
from a2a_scorecard.scan import run_scan
from a2a_scorecard.transport import (
    HostPacer,
    ScanLimits,
    ScanTransport,
    Throttled,
    _default_host_key,
    parse_retry_after,
)

SETTINGS = Settings(allow_http=True)


class FakeClock:
    """A monotonic-shaped clock that only ever moves when told to."""

    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, delta: float) -> None:
        self.now += delta


def recording_sleep(clock: FakeClock, calls: list[float]):  # -> Callable[[float], None]
    def sleep(seconds: float) -> None:
        calls.append(seconds)
        clock.advance(seconds)

    return sleep


# --- HostPacer pacing arithmetic -------------------------------------------------


def test_pacer_waits_out_remaining_pace_for_same_key() -> None:
    clock = FakeClock()
    sleeps: list[float] = []
    pacer = HostPacer(0.5, clock=clock, sleep=recording_sleep(clock, sleeps))

    with pacer.slot("host-a"):
        pass
    clock.advance(0.1)  # only 0.1s of the 0.5s pace has elapsed
    with pacer.slot("host-a"):
        pass

    assert sleeps == [pytest.approx(0.4)]


def test_pacer_does_not_wait_once_pace_has_fully_elapsed() -> None:
    clock = FakeClock()
    sleeps: list[float] = []
    pacer = HostPacer(0.5, clock=clock, sleep=recording_sleep(clock, sleeps))

    with pacer.slot("host-a"):
        pass
    clock.advance(0.5)
    with pacer.slot("host-a"):
        pass

    assert sleeps == []


def test_pacer_keys_are_independent() -> None:
    clock = FakeClock()
    sleeps: list[float] = []
    pacer = HostPacer(0.5, clock=clock, sleep=recording_sleep(clock, sleeps))

    with pacer.slot("host-a"):
        pass
    with pacer.slot("host-b"):
        pass  # different key: must not wait out host-a's pace

    assert sleeps == []


def test_pacer_key_callable_is_applied() -> None:
    clock = FakeClock()
    sleeps: list[float] = []
    pacer = HostPacer(
        0.5, key=lambda raw: raw.lower(), clock=clock, sleep=recording_sleep(clock, sleeps)
    )

    with pacer.slot("HOST-A"):
        pass
    with pacer.slot("host-a"):  # same key once lowercased
        pass

    assert sleeps == [pytest.approx(0.5)]


# --- _default_host_key: httpx.URL and bare hostname must key identically ----------
#
# Regression coverage for the bug fixed by adding a module-level
# `_default_host_key` (ADR-0020): the default key function used to be
# `lambda url: url.host`, which raised AttributeError when called with a
# plain hostname string (as the TLS check's raw-socket pacer slot does),
# because `str` has no `.host` attribute. That crash was caught by scan.py's
# blanket `except Exception` and scored as ERROR on every HTTPS target - see
# tests/test_tls.py for the check-level regression test. This test covers
# the load-bearing property directly: an httpx.URL and the bare hostname
# string it carries must produce the SAME pacing key, or the raw TLS
# handshake and the httpx requests to the same host would pace
# independently instead of serializing together.


def test_default_host_key_matches_for_url_and_bare_hostname() -> None:
    url = httpx.URL("https://example.invalid:8443/path")
    assert _default_host_key(url) == "example.invalid"
    assert _default_host_key("example.invalid") == _default_host_key(url)


def test_default_host_key_accepts_bare_hostname_without_raising() -> None:
    # Before the fix, this raised AttributeError: 'str' object has no
    # attribute 'host'.
    assert _default_host_key("example.invalid") == "example.invalid"


def test_host_pacer_with_default_key_serializes_url_and_bare_hostname() -> None:
    """The same property, exercised through `HostPacer` built the way
    `ScanTransport` builds its default one, rather than calling
    `_default_host_key` directly."""
    clock = FakeClock()
    sleeps: list[float] = []
    pacer = HostPacer(0.5, key=_default_host_key, clock=clock, sleep=recording_sleep(clock, sleeps))

    with pacer.slot(httpx.URL("https://example.invalid/")):
        pass
    with pacer.slot("example.invalid"):  # same key: must wait out the pace
        pass

    assert sleeps == [pytest.approx(0.5)]


# --- Retry-After header parsing ---------------------------------------------------


def test_parse_retry_after_delta_seconds() -> None:
    assert parse_retry_after("5", default_s=99.0) == 5.0


def test_parse_retry_after_missing_defaults() -> None:
    assert parse_retry_after(None, default_s=3.0) == 3.0


def test_parse_retry_after_http_date() -> None:
    future = datetime.datetime.now(datetime.UTC) + datetime.timedelta(seconds=10)
    header = format_datetime(future)
    delay = parse_retry_after(header, default_s=99.0)
    # format_datetime truncates to whole seconds and the assertion runs a
    # moment later, so allow a couple of seconds of slack either way.
    assert 7.0 <= delay <= 10.5


def test_parse_retry_after_garbage_defaults() -> None:
    assert parse_retry_after("soon", default_s=7.0) == 7.0


def test_parse_retry_after_huge_value_returned_verbatim() -> None:
    # Capping is the transport's job, not the parser's: it just parses.
    assert parse_retry_after("86400", default_s=5.0) == 86400.0


# --- ScanTransport 429 handling, via the fake agent --------------------------------


def test_throttle_once_sleeps_exactly_one_second(fake_agent) -> None:
    url = fake_agent("throttle-once")
    sleeps: list[float] = []
    transport = ScanTransport(sleep=lambda s: sleeps.append(s))

    report = run_scan(url, SETTINGS, transport=transport)

    # The throttle fires once, with Retry-After: 1, and is retried exactly
    # once. Other entries in `sleeps` (if any) are the unrelated 0.5s
    # per-host pacing between this scan's later same-host requests, not the
    # throttle retry - so assert on the throttle sleep specifically rather
    # than on the whole list.
    assert sleeps.count(1.0) == 1
    by_id = {r.check_id: r for r in report.results}
    assert by_id["C001"].status is CheckStatus.PASS


def test_throttle_always_raises_throttled(fake_agent) -> None:
    url = fake_agent("throttle-always")
    transport = ScanTransport(sleep=lambda s: None)

    with pytest.raises(Throttled):
        run_scan(url, SETTINGS, transport=transport)


def test_throttle_post_propagates_out_of_run_scan(fake_agent) -> None:
    """Regression test for the scan.py swallow (ADR-0020): before scan.py
    re-raised ScanAborted ahead of its blanket except Exception, a throttled
    POST was silently turned into a scored ERROR result instead of aborting
    the scan."""
    url = fake_agent("throttle-post")
    transport = ScanTransport(sleep=lambda s: None)

    with pytest.raises(Throttled):
        run_scan(url, SETTINGS, transport=transport)

    posts = [entry for entry in fake_agent.journal(url) if entry[2] == "POST"]
    # Never retried: exactly the one SendMessage ping that got throttled,
    # holding the two-ping-per-scan budget even on the abort path.
    assert len(posts) == 1


def test_throttle_http_date_does_not_raise(fake_agent) -> None:
    url = fake_agent("throttle-http-date")
    transport = ScanTransport(sleep=lambda s: None)

    report = run_scan(url, SETTINGS, transport=transport)

    by_id = {r.check_id: r for r in report.results}
    assert by_id["C001"].status is CheckStatus.PASS


def test_throttle_garbage_retry_after_does_not_raise(fake_agent) -> None:
    url = fake_agent("throttle-garbage")
    transport = ScanTransport(limits=ScanLimits(retry_after_default_s=0.01), sleep=lambda s: None)

    report = run_scan(url, SETTINGS, transport=transport)

    by_id = {r.check_id: r for r in report.results}
    assert by_id["C001"].status is CheckStatus.PASS


def test_throttle_huge_retry_after_aborts_without_sleeping(fake_agent) -> None:
    url = fake_agent("throttle-huge")
    sleeps: list[float] = []
    transport = ScanTransport(sleep=lambda s: sleeps.append(s))

    with pytest.raises(Throttled):
        run_scan(url, SETTINGS, transport=transport)

    assert sleeps == []  # over the cap: abort without ever sleeping


# --- The pacer keys on the real request host, not the target ----------------------


def test_pacer_keys_on_real_request_host_not_declared_target(fake_agent) -> None:
    """The card served by `primary` declares its JSON-RPC interface at
    `secondary` - a different fixture server (ADR-0020). If the pacer keyed
    on the target's own host rather than each request's actual host, every
    request to `secondary` would also wait out `primary`'s pace slot,
    producing more sleeps than the two hosts' own request counts justify.
    """
    primary = fake_agent("cross-host-interface")
    secondary = fake_agent("compliant")
    fake_agent.server_for(primary).second_server_url = secondary

    clock = FakeClock()
    sleeps: list[float] = []
    # Both fixture servers are on 127.0.0.1, distinguished only by port, so
    # the key must be the netloc here - production's default key (host
    # only) is what this test exists to prove is *not* what's used for
    # cross-host distinction; see HostPacer's docstring in transport.py.
    transport = ScanTransport(
        clock=clock,
        sleep=recording_sleep(clock, sleeps),
        host_key=lambda url: f"{url.host}:{url.port}",
    )

    report = run_scan(primary, SETTINGS, transport=transport)

    by_id = {r.check_id: r for r in report.results}
    assert by_id["C020"].status is CheckStatus.PASS

    primary_posts = [e for e in fake_agent.journal(primary) if e[2] == "POST"]
    secondary_posts = [e for e in fake_agent.journal(secondary) if e[2] == "POST"]
    assert primary_posts == []
    assert len(secondary_posts) == 2  # SendMessage ping + unknown-method probe

    # primary: 2 GETs (C001, C010) -> 1 wait. secondary: 2 POSTs -> 1 wait.
    # A shared/mis-keyed pacer would produce 3 waits across the 4 requests.
    assert len(sleeps) == 2
