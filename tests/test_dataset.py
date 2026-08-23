"""Tests for src/a2a_scorecard/dataset.py (ADR-0021).

Pure-data tests: `BatchRecord`s are constructed directly, never produced by
driving a real scan, and nothing here talks to the fake agent or the
network. Writes only to `tmp_path`.
"""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path

from a2a_scorecard import dataset, methodology
from a2a_scorecard.batch import BatchOutcome, BatchRecord
from a2a_scorecard.grading import GRADING_VERSION
from a2a_scorecard.models import CheckResult, CheckStatus, TargetReport
from a2a_scorecard.schema import SPEC_VERSION
from a2a_scorecard.targets import Source, Target

_NOW = datetime(2026, 8, 22, 12, 0, 0, tzinfo=UTC)
_COMMIT = "deadbeefcafefeed0000000000000000000000"


def _target(target: str = "https://agent.example.com", operator: str = "example.com") -> Target:
    return Target(
        target=target,
        operator=operator,
        sources=[
            Source(
                directory="a2a-registry.org",
                ref="https://a2a-registry.org",
                kind="registry",
                observed_at="2026-08-22",
            )
        ],
        first_seen="2026-08-22",
    )


def _report(target_url: str) -> TargetReport:
    return TargetReport(
        target=target_url,
        scanned_at="2026-08-22T12:00:00Z",
        scanner_version="0.3.0",
        grading_version=GRADING_VERSION,
        spec_generation=SPEC_VERSION,
        results=[
            CheckResult(
                check_id="C001",
                title="Agent card is reachable",
                status=CheckStatus.PASS,
                weight=10,
                evidence="200 OK",
                details={"status_code": 200},
            ),
        ],
        score=100.0,
        grade="A",
        applicable_weight=10,
        max_weight=10,
    )


def _ok_record(target: Target, started_at: float = 1000.0) -> BatchRecord:
    return BatchRecord(
        target_id=target.target_id,
        target_url=target.target,
        operator=target.operator,
        outcome=BatchOutcome.OK,
        report=_report(target.target),
        started_at=started_at,
        finished_at=started_at + 1.5,
    )


def _writer(
    path: Path,
    *,
    run_id: str = "run-20260822T120000Z",
    targets: list[Target] | None = None,
    target_list_path: Path | None = None,
    now: datetime = _NOW,
) -> dataset.RunWriter:
    return dataset.RunWriter(
        path,
        run_id=run_id,
        targets=targets or [],
        target_list_path=target_list_path,
        now=now,
        git_commit=_COMMIT,
    )


# --- round trip -----------------------------------------------------------


def test_round_trip_header_targets_footer(tmp_path: Path) -> None:
    path = tmp_path / "run-20260822T120000Z.jsonl"
    targets = [
        _target("https://a.example.com", "a.example.com"),
        _target("https://b.example.com", "b.example.com"),
    ]

    with _writer(path, targets=targets) as writer:
        for t in targets:
            writer(_ok_record(t))

    run = dataset.read_run(path)
    assert run.header is not None
    assert run.header["record_type"] == "run_start"
    assert run.header["run_id"] == "run-20260822T120000Z"
    assert run.header["git_commit"] == _COMMIT
    assert run.header["spec_version"] == SPEC_VERSION
    assert run.header["grading_version"] == GRADING_VERSION
    assert run.header["grading_manifest_digest"] == methodology.manifest_digest()
    assert run.header["grading_manifest"] == methodology.manifest()

    assert len(run.targets) == 2
    for row in run.targets:
        assert row["record_type"] == "target"
        assert row["run_id"] == "run-20260822T120000Z"
        assert row["scanner_version"]
        assert row["grading_version"] == GRADING_VERSION
        assert row["spec_version"] == SPEC_VERSION
        assert row["grading_manifest_digest"] == methodology.manifest_digest()
        assert row["provenance"] == [
            {
                "directory": "a2a-registry.org",
                "ref": "https://a2a-registry.org",
                "kind": "registry",
                "observed_at": "2026-08-22",
            }
        ]

    assert run.footer is not None
    assert run.footer["record_type"] == "run_end"
    assert run.footer["targets_attempted"] == 2
    assert run.footer["outcomes"] == {"ok": 2}
    assert run.footer["aborted"] is False
    assert run.complete is True


def test_report_stored_unprojected_preserves_weight_and_evidence(tmp_path: Path) -> None:
    """The exact regression the census harness introduced: storing a
    {check_id: status} map instead of the full report silently discarded
    weight and evidence. Assert both survive the round trip."""
    path = tmp_path / "run.jsonl"
    target = _target()

    with _writer(path, targets=[target]) as writer:
        writer(_ok_record(target))

    run = dataset.read_run(path)
    report = run.targets[0]["report"]
    assert report is not None
    [check] = report["results"]
    assert check["check_id"] == "C001"
    assert check["weight"] == 10
    assert check["evidence"] == "200 OK"
    assert check["details"] == {"status_code": 200}
    assert report["score"] == 100.0
    assert report["grade"] == "A"


# --- torn tail --------------------------------------------------------------


def test_repair_torn_tail_discards_only_the_fragment(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    target = _target()

    with _writer(path, targets=[target]) as writer:
        writer(_ok_record(target))
    # The writer above wrote a clean run_end footer; append a torn line to
    # simulate a process killed mid-write on a *resumed* file.
    good_size = path.stat().st_size
    with open(path, "a", encoding="utf-8") as fh:
        fh.write('{"record_type": "target", "target_id": "https://c.exampl')

    discarded = dataset.repair_torn_tail(path)
    assert discarded > 0
    assert path.stat().st_size == good_size

    # Earlier records are intact.
    run = dataset.read_run(path)
    assert run.header is not None
    assert len(run.targets) == 1
    assert run.footer is not None

    # A subsequent append lands on a clean line.
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"record_type": "marker"}) + "\n")
    text = path.read_text()
    assert text.count("\n") == text.rstrip("\n").count("\n") + 1
    lines = [line for line in text.splitlines() if line]
    for line in lines:
        json.loads(line)  # every line parses


def test_repair_torn_tail_no_op_on_clean_file(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    target = _target()
    with _writer(path, targets=[target]) as writer:
        writer(_ok_record(target))
    before = path.read_bytes()
    assert dataset.repair_torn_tail(path) == 0
    assert path.read_bytes() == before


# --- completed_targets / resume ---------------------------------------------


def test_completed_targets_on_footerless_file(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    a = _target("https://a.example.com", "a.example.com")
    b = _target("https://b.example.com", "b.example.com")

    writer = _writer(path, targets=[a, b])
    writer(_ok_record(a))
    writer(_ok_record(b))
    # Deliberately no close(): simulates a killed run. No footer present.

    run = dataset.read_run(path)
    assert run.footer is None
    assert run.complete is False

    ids = dataset.completed_targets(path)
    assert ids == {a.target_id, b.target_id}


def test_no_footer_written_on_exception(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    target = _target()

    class _Boom(Exception):
        pass

    try:
        with _writer(path, targets=[target]) as writer:
            writer(_ok_record(target))
            raise _Boom("simulated crash mid-run")
    except _Boom:
        pass

    run = dataset.read_run(path)
    assert run.header is not None
    assert len(run.targets) == 1
    assert run.footer is None


def test_aborted_flag_distinguishes_breaker_trip_from_crash(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    target = _target()

    with _writer(path, targets=[target]) as writer:
        writer(_ok_record(target))
        writer.close(aborted=True)

    run = dataset.read_run(path)
    assert run.footer is not None
    assert run.footer["aborted"] is True


# --- absences are not failures ----------------------------------------------


def test_absences_written_with_null_report_and_excluded_from_footer_counts(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    ok_target = _target("https://a.example.com", "a.example.com")
    excluded_target = _target("https://b.example.com", "b.example.com")
    throttled_target = _target("https://c.example.com", "c.example.com")

    excluded_record = BatchRecord(
        target_id=excluded_target.target_id,
        target_url=excluded_target.target,
        operator=excluded_target.operator,
        outcome=BatchOutcome.EXCLUDED,
        started_at=10.0,
        finished_at=10.0,
    )
    throttled_record = BatchRecord(
        target_id=throttled_target.target_id,
        target_url=throttled_target.target,
        operator=throttled_target.operator,
        outcome=BatchOutcome.THROTTLED,
        error="429",
        started_at=20.0,
        finished_at=20.5,
    )

    with _writer(path, targets=[ok_target, excluded_target, throttled_target]) as writer:
        writer(_ok_record(ok_target))
        writer(excluded_record)
        writer(throttled_record)

    run = dataset.read_run(path)
    by_outcome = {row["outcome"]: row for row in run.targets}
    assert by_outcome["excluded"]["report"] is None
    assert by_outcome["throttled"]["report"] is None
    assert by_outcome["ok"]["report"] is not None

    assert run.footer is not None
    counts = run.footer["outcomes"]
    assert counts == {"ok": 1, "excluded": 1, "throttled": 1}
    # No aggregate "failure" bucket exists at all: only the outcome taxonomy.
    assert set(counts) <= {o.value for o in BatchOutcome}


# --- thread safety ------------------------------------------------------


def test_concurrent_writes_from_multiple_threads_all_land(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    n_threads = 8
    per_thread = 25
    total = n_threads * per_thread
    targets = [_target(f"https://t{i}.example.com", f"t{i}.example.com") for i in range(total)]

    writer = _writer(path, targets=targets)
    errors: list[Exception] = []

    def worker(offset: int) -> None:
        try:
            for j in range(per_thread):
                t = targets[offset * per_thread + j]
                writer(_ok_record(t, started_at=1000.0 + offset * per_thread + j))
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    writer.close()

    assert errors == []

    run = dataset.read_run(path)
    assert len(run.targets) == n_threads * per_thread
    seen_ids = {row["target_id"] for row in run.targets}
    assert seen_ids == {t.target_id for t in targets}

    # Every physical line parses: the lock did not let writes interleave.
    lines = [line for line in path.read_text().splitlines() if line]
    assert len(lines) == n_threads * per_thread + 2  # header + footer
    for line in lines:
        json.loads(line)


# --- rebuild_index ------------------------------------------------------


def test_rebuild_index_takes_most_recent_last_scanned_at(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    target = _target()

    path1 = runs_dir / "run-20260820T000000Z.jsonl"
    with _writer(
        path1,
        run_id="run-20260820T000000Z",
        targets=[target],
        now=datetime(2026, 8, 20, tzinfo=UTC),
    ) as writer:
        writer(_ok_record(target, started_at=1_755_648_000.0))  # 2025-08-20-ish epoch stand-in

    path2 = runs_dir / "run-20260822T000000Z.jsonl"
    with _writer(
        path2,
        run_id="run-20260822T000000Z",
        targets=[target],
        now=datetime(2026, 8, 22, tzinfo=UTC),
    ) as writer:
        writer(_ok_record(target, started_at=1_755_820_800.0))  # later than path1's timestamp

    index = dataset.rebuild_index(runs_dir)
    assert {r["run_id"] for r in index["runs"]} == {"run-20260820T000000Z", "run-20260822T000000Z"}

    later_iso = dataset._iso_from_epoch(1_755_820_800.0)
    earlier_iso = dataset._iso_from_epoch(1_755_648_000.0)
    assert index["last_scanned_at"][target.target_id] == later_iso
    assert index["last_scanned_at"][target.target_id] != earlier_iso


def test_rebuild_index_on_empty_dir(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    index = dataset.rebuild_index(runs_dir)
    assert index == {"runs": [], "last_scanned_at": {}}


def test_rebuild_index_includes_incomplete_run(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    target = _target()
    path = runs_dir / "run-20260822T000000Z.jsonl"
    writer = _writer(path, run_id="run-20260822T000000Z", targets=[target])
    writer(_ok_record(target))
    # No close(): incomplete run, still contributes its target record.

    index = dataset.rebuild_index(runs_dir)
    assert len(index["runs"]) == 1
    assert index["runs"][0]["ended_at"] is None
    assert target.target_id in index["last_scanned_at"]
