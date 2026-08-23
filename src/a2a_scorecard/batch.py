"""Operator-grouped batch scanning: scheduling, quarantine, budgets, and the
outcome taxonomy (ADR-0020).

One worker owns a whole operator group and walks it sequentially; a thread
pool runs groups concurrently. Because a host belongs to exactly one
operator unit, serializing per group implies serializing per host - and a
`ScanTransport`'s own per-host pacer (see transport.py) additionally covers
the case where a card's declared interface points at a host the grouping
never saw.

The dataset writer lands in a later step (ADR-0021); `writer` here is only
the seam it will plug into.
"""

from __future__ import annotations

import enum
import threading
import time
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Protocol

from a2a_scorecard.config import Settings
from a2a_scorecard.models import TargetReport
from a2a_scorecard.scan import run_scan
from a2a_scorecard.targets import Exclusion, Target, apply_exclusions
from a2a_scorecard.transport import (
    RequestBudgetExceeded,
    ScanAborted,
    ScanDeadlineExceeded,
    ScanLimits,
    ScanTransport,
    Throttled,
)


class BatchOutcome(enum.StrEnum):
    """Recorded verbatim per target (ADR-0020). Only OK carries a report
    and a grade; every other member is an absence and must never be
    aggregated as a failure."""

    OK = "ok"
    ERROR = "error"
    THROTTLED = "throttled"
    BUDGET_EXCEEDED = "budget_exceeded"
    DEADLINE_EXCEEDED = "deadline_exceeded"
    SKIPPED_RECENT = "skipped_recent"
    SKIPPED_THROTTLED_GROUP = "skipped_throttled_group"
    EXCLUDED = "excluded"


@dataclass
class BatchRecord:
    """One target's outcome from a batch run. `report` is set only for
    `BatchOutcome.OK`; every other outcome is an absence, per the ADR."""

    target_id: str
    target_url: str
    operator: str
    outcome: BatchOutcome
    report: TargetReport | None = None
    error: str | None = None
    started_at: float = 0.0
    finished_at: float = 0.0

    @property
    def elapsed_s(self) -> float:
        return max(0.0, self.finished_at - self.started_at)


class BatchWriter(Protocol):
    """The seam the dataset writer (ADR-0021) will plug into. Called once
    per target, including for absences (excluded, skipped, throttled, ...).
    Implementations that persist state are responsible for their own
    thread-safety: `run_batch` calls this from whichever operator group's
    worker thread produced the record."""

    def __call__(self, record: BatchRecord) -> None: ...


@dataclass
class BatchConfig:
    """Tunables for one `run_batch` call. Defaults are ADR-0020's numbers."""

    # Concurrency default 8, clamped to [1, 16]: empirically grounded by the
    # 2026-08-22 census (400 targets, 8 workers, zero 429s observed).
    # Raising it buys nothing measurable and increases simultaneous load on
    # shared PaaS infrastructure.
    concurrency: int = 8
    within_operator_pause_s: float = 3.0
    # Re-scan floor: at most one scan per target per day. Zero here is only
    # ever set by tests - the CLI exposes no flag to lower it, because
    # policy floors are not command-line arguments.
    rescan_interval_s: float = 86400.0
    # Twenty-five consecutive `error` outcomes aborts the whole run: that
    # many failures in an unattended run means our egress is broken, not
    # that the ecosystem died.
    circuit_breaker_threshold: int = 25
    settings: Settings = field(default_factory=Settings)
    limits: ScanLimits = field(default_factory=ScanLimits)
    exclusions: list[Exclusion] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.concurrency = max(1, min(16, self.concurrency))


@dataclass
class BatchSummary:
    """Aggregate counts from one `run_batch` call."""

    total: int = 0
    outcomes: dict[BatchOutcome, int] = field(default_factory=dict)
    # Set when the circuit breaker fired; targets not yet started when it
    # fired have no record at all (the run stopped, it did not fail them).
    breaker_tripped: bool = False

    def record(self, outcome: BatchOutcome) -> None:
        self.total += 1
        self.outcomes[outcome] = self.outcomes.get(outcome, 0) + 1


class _CircuitBreaker:
    """Global, cross-group consecutive-error counter (ADR-0020). "Consecutive"
    is inherently approximate once groups run concurrently - a trip only
    guarantees that at least `threshold` `error` outcomes landed without an
    intervening non-error outcome being observed by this counter, not a
    strict global ordering. That's the point: it's a breaker for "our
    egress is broken", not a precise audit trail."""

    def __init__(self, threshold: int) -> None:
        self._threshold = threshold
        self._consecutive_errors = 0
        self._lock = threading.Lock()
        self.tripped = False

    def update(self, outcome: BatchOutcome) -> None:
        with self._lock:
            if outcome is BatchOutcome.ERROR:
                self._consecutive_errors += 1
                if self._consecutive_errors >= self._threshold:
                    self.tripped = True
            else:
                self._consecutive_errors = 0


def _now_record(target: Target, outcome: BatchOutcome, clock: Callable[[], float]) -> BatchRecord:
    now = clock()
    return BatchRecord(
        target_id=target.target_id,
        target_url=target.target,
        operator=target.operator,
        outcome=outcome,
        started_at=now,
        finished_at=now,
    )


def _scan_one(
    target: Target,
    config: BatchConfig,
    clock: Callable[[], float],
    sleep: Callable[[float], None],
) -> BatchRecord:
    started = clock()
    transport = ScanTransport(limits=config.limits, clock=clock, sleep=sleep)
    report: TargetReport | None = None
    error: str | None = None
    try:
        report = run_scan(target.target, config.settings, transport=transport)
        outcome = BatchOutcome.OK
    except Throttled as exc:
        outcome = BatchOutcome.THROTTLED
        error = str(exc)
    except RequestBudgetExceeded as exc:
        outcome = BatchOutcome.BUDGET_EXCEEDED
        error = str(exc)
    except ScanDeadlineExceeded as exc:
        outcome = BatchOutcome.DEADLINE_EXCEEDED
        error = str(exc)
    except ScanAborted as exc:  # pragma: no cover - defensive: a future ScanAborted subclass
        outcome = BatchOutcome.ERROR
        error = str(exc)
    except Exception as exc:  # noqa: BLE001 - one bad target must not stop the batch
        outcome = BatchOutcome.ERROR
        error = f"{type(exc).__name__}: {exc}"
    finished = clock()
    return BatchRecord(
        target_id=target.target_id,
        target_url=target.target,
        operator=target.operator,
        outcome=outcome,
        report=report,
        error=error,
        started_at=started,
        finished_at=finished,
    )


def run_batch(
    targets: Iterable[Target],
    writer: BatchWriter,
    config: BatchConfig | None = None,
    already_done: Callable[[str], float | None] | None = None,
    clock: Callable[[], float] = time.time,
    sleep: Callable[[float], None] = time.sleep,
) -> BatchSummary:
    """Scan `targets`, writing one `BatchRecord` per target via `writer`.

    `already_done(target_id)` returns the epoch timestamp of that target's
    last scan, or None; a target scanned within `config.rescan_interval_s`
    of `clock()` is recorded `skipped_recent` rather than scanned again.
    `clock`/`sleep` are injected end to end - into the batch's own
    inter-target pause and into each target's `ScanTransport` - so tests can
    run the whole scheduler in zero wall-clock time.
    """
    config = config or BatchConfig()
    already_done = already_done or (lambda target_id: None)
    summary = BatchSummary()
    summary_lock = threading.Lock()
    breaker = _CircuitBreaker(config.circuit_breaker_threshold)

    kept, excluded = apply_exclusions(list(targets), config.exclusions)

    def emit(record: BatchRecord) -> None:
        writer(record)
        with summary_lock:
            summary.record(record.outcome)

    for target in excluded:
        emit(_now_record(target, BatchOutcome.EXCLUDED, clock))

    groups: dict[str, list[Target]] = {}
    for target in kept:
        groups.setdefault(target.operator, []).append(target)

    # Longest-first so a large operator does not become the run's tail;
    # members sorted by normalised URL so a resumed run replays
    # deterministically (ADR-0020). Ties broken by operator name for a
    # stable overall order.
    ordered_groups = [
        sorted(members, key=lambda t: t.target_id)
        for _operator, members in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    ]

    def run_group(members: list[Target]) -> None:
        quarantined = False
        for i, target in enumerate(members):
            if breaker.tripped:
                return
            if quarantined:
                emit(_now_record(target, BatchOutcome.SKIPPED_THROTTLED_GROUP, clock))
                continue
            last = already_done(target.target_id)
            if last is not None and (clock() - last) < config.rescan_interval_s:
                emit(_now_record(target, BatchOutcome.SKIPPED_RECENT, clock))
                continue

            record = _scan_one(target, config, clock, sleep)
            emit(record)
            breaker.update(record.outcome)
            if record.outcome is BatchOutcome.THROTTLED:
                # A host that said stop should not receive three more scans
                # from us in the next ten seconds: quarantine the rest of
                # its operator group for this run (ADR-0020).
                quarantined = True
            if breaker.tripped:
                summary.breaker_tripped = True
                return
            if i + 1 < len(members):
                sleep(config.within_operator_pause_s)

    with ThreadPoolExecutor(max_workers=config.concurrency) as pool:
        list(pool.map(run_group, ordered_groups))

    return summary
