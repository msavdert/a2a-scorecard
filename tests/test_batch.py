"""Tests for `a2a_scorecard.batch`: operator-group scheduling, per-host
pacing as observed across a whole run, throttle quarantine, the circuit
breaker, and the re-scan floor (ADR-0020).

Tests never touch the network: every target here points at the in-process
fake agent (CLAUDE.md rule 2).
"""

from __future__ import annotations

import threading
import time

import pytest

from a2a_scorecard import batch as batch_module
from a2a_scorecard.batch import BatchConfig, BatchOutcome, BatchRecord, run_batch
from a2a_scorecard.targets import Source, Target

SOURCE = Source(directory="test", ref="test", kind="registry", observed_at="2026-01-01")


def _target(url: str, operator: str) -> Target:
    return Target(target=url, operator=operator, sources=[SOURCE], first_seen="2026-01-01")


class ListWriter:
    """Trivial in-memory `BatchWriter` (the dataset writer lands in a later
    step per ADR-0020/0021; this is only the seam's test double)."""

    def __init__(self) -> None:
        self.records: list[BatchRecord] = []
        self._lock = threading.Lock()

    def __call__(self, record: BatchRecord) -> None:
        with self._lock:
            self.records.append(record)


# --- Per-host serialization across a whole batch, not just within one scan --------


def test_per_host_requests_never_overlap(fake_agent) -> None:
    # "slow" mode gives each request real, non-zero duration so an overlap
    # would actually show up in the journal instead of two near-instant
    # local requests happening to not visibly overlap by luck.
    host_a = fake_agent("slow", host="127.0.0.1")
    host_b = fake_agent("slow", host="127.0.0.2")
    targets = [
        _target(host_a, "op-a"),
        _target(host_a, "op-a"),
        _target(host_b, "op-b"),
        _target(host_b, "op-b"),
    ]
    writer = ListWriter()
    config = BatchConfig(concurrency=2, within_operator_pause_s=0.0, rescan_interval_s=0.0)

    run_batch(targets, writer, config, sleep=lambda s: None)

    for url in (host_a, host_b):
        journal = fake_agent.journal(url)
        assert len(journal) >= 2  # sanity: both targets on this host actually ran
        intervals = sorted((entry[0], entry[1]) for entry in journal)
        for (_start1, end1), (start2, _end2) in zip(intervals, intervals[1:], strict=False):
            assert end1 <= start2, f"overlapping requests to {url}: {intervals}"


# --- Cross-host parallelism: two operator groups actually run concurrently --------


def test_cross_host_groups_run_concurrently(fake_agent) -> None:
    """A `threading.Barrier` of 2 parties, one per host's first request.

    If `run_batch` serialized the two operator groups instead of running
    them concurrently, the first group would block on the barrier until the
    second (which never arrives - it hasn't started) times out, and the
    whole call would take close to `barrier_timeout`. A concurrent runner
    satisfies the barrier almost immediately.
    """
    barrier = threading.Barrier(2)
    barrier_timeout = 2.0
    host_a = fake_agent("barrier", host="127.0.0.1")
    host_b = fake_agent("barrier", host="127.0.0.2")
    for url in (host_a, host_b):
        server = fake_agent.server_for(url)
        server.barrier = barrier
        server.barrier_timeout = barrier_timeout

    targets = [_target(host_a, "op-a"), _target(host_b, "op-b")]
    writer = ListWriter()
    config = BatchConfig(concurrency=2, within_operator_pause_s=0.0, rescan_interval_s=0.0)

    started = time.monotonic()
    run_batch(targets, writer, config, sleep=lambda s: None)
    elapsed = time.monotonic() - started

    assert elapsed < barrier_timeout - 0.5, (
        f"took {elapsed:.2f}s: groups were not scheduled concurrently"
    )
    outcomes = {r.target_url: r.outcome for r in writer.records}
    assert outcomes[host_a] is BatchOutcome.OK
    assert outcomes[host_b] is BatchOutcome.OK


# --- Throttle quarantines the rest of its operator group ---------------------------


def test_throttle_quarantines_rest_of_operator_group(fake_agent) -> None:
    # Distinct 127.0.0.0/8 addresses so target_id sort order (and thus
    # which target the group hits first) is deterministic regardless of
    # the OS-assigned ephemeral port.
    throttled_host = fake_agent("throttle-always", host="127.0.0.1")
    sibling_a = fake_agent("compliant", host="127.0.0.2")
    sibling_b = fake_agent("compliant", host="127.0.0.3")
    # Same operator group; sorted by target_id, so order is deterministic
    # once bound to distinct 127.0.0.0/8 addresses (see fake_agent.make).
    targets = [
        _target(throttled_host, "op-quarantine"),
        _target(sibling_a, "op-quarantine"),
        _target(sibling_b, "op-quarantine"),
    ]
    writer = ListWriter()
    config = BatchConfig(concurrency=1, within_operator_pause_s=0.0, rescan_interval_s=0.0)

    run_batch(targets, writer, config, sleep=lambda s: None)

    by_url = {r.target_url: r for r in writer.records}
    assert by_url[throttled_host].outcome is BatchOutcome.THROTTLED
    assert by_url[sibling_a].outcome is BatchOutcome.SKIPPED_THROTTLED_GROUP
    assert by_url[sibling_b].outcome is BatchOutcome.SKIPPED_THROTTLED_GROUP
    # The quarantined siblings were never contacted at all.
    assert fake_agent.journal(sibling_a) == []
    assert fake_agent.journal(sibling_b) == []


# --- Global circuit breaker: 25 consecutive errors aborts the whole run ------------


def test_circuit_breaker_unit_trips_at_threshold() -> None:
    breaker = batch_module._CircuitBreaker(3)
    breaker.update(BatchOutcome.ERROR)
    breaker.update(BatchOutcome.ERROR)
    assert breaker.tripped is False
    breaker.update(BatchOutcome.ERROR)
    assert breaker.tripped is True


def test_circuit_breaker_unit_resets_on_non_error() -> None:
    breaker = batch_module._CircuitBreaker(3)
    breaker.update(BatchOutcome.ERROR)
    breaker.update(BatchOutcome.ERROR)
    breaker.update(BatchOutcome.OK)  # resets the streak
    breaker.update(BatchOutcome.ERROR)
    breaker.update(BatchOutcome.ERROR)
    assert breaker.tripped is False


def test_circuit_breaker_stops_run_batch(monkeypatch: pytest.MonkeyPatch) -> None:
    """25 consecutive `error` outcomes (here, 5 - the config overrides the
    default threshold) abort the run: targets not yet started get no
    record at all, per the ADR."""

    def always_raises(url: str, settings=None, *, transport=None):  # noqa: ANN001, ANN003
        raise RuntimeError(f"simulated failure for {url}")

    monkeypatch.setattr(batch_module, "run_scan", always_raises)

    # One target per operator so each group's single member trips the
    # breaker check for the *next* group, not a later member of its own.
    targets = [_target(f"http://target-{i}.invalid", f"op-{i}") for i in range(30)]
    writer = ListWriter()
    config = BatchConfig(
        concurrency=1,  # strictly sequential: makes "consecutive" unambiguous
        within_operator_pause_s=0.0,
        rescan_interval_s=0.0,
        circuit_breaker_threshold=5,
    )

    summary = run_batch(targets, writer, config, sleep=lambda s: None)

    assert summary.breaker_tripped is True
    assert len(writer.records) == 5
    assert all(r.outcome is BatchOutcome.ERROR for r in writer.records)


# --- Re-scan floor: `already_done` skips a recently-scanned target ----------------


def test_already_done_skips_recent_target_with_zero_requests(fake_agent) -> None:
    url = fake_agent("compliant")
    target = _target(url, "op-resume")
    writer = ListWriter()
    config = BatchConfig(concurrency=1, within_operator_pause_s=0.0, rescan_interval_s=100.0)

    summary = run_batch(
        [target],
        writer,
        config,
        already_done=lambda target_id: 0.0,
        clock=lambda: 50.0,  # 50s since the recorded scan, under the 100s floor
        sleep=lambda s: None,
    )

    assert summary.outcomes == {BatchOutcome.SKIPPED_RECENT: 1}
    assert writer.records[0].outcome is BatchOutcome.SKIPPED_RECENT
    assert fake_agent.journal(url) == []


def test_already_done_rescans_once_interval_elapsed(fake_agent) -> None:
    url = fake_agent("compliant")
    target = _target(url, "op-resume")
    writer = ListWriter()
    config = BatchConfig(concurrency=1, within_operator_pause_s=0.0, rescan_interval_s=100.0)

    run_batch(
        [target],
        writer,
        config,
        already_done=lambda target_id: 0.0,
        clock=lambda: 200.0,  # 200s since the recorded scan, over the 100s floor
        sleep=lambda s: None,
    )

    assert writer.records[0].outcome is BatchOutcome.OK
    assert fake_agent.journal(url) != []
