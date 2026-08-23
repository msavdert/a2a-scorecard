"""Tests for the aggregate ecosystem report generator (ecosystem.py).

Pure-data only: every fixture here is a hand-built `dataset.RunFile` (or,
in the RunWriter integration test, a small run file written to a tmp_path
via `dataset.RunWriter`). Nothing drives a scan and nothing talks to the
fake agent in conftest.py - ecosystem.py consumes already-parsed dataset
records, so that's all these tests construct.
"""

from __future__ import annotations

import random
import re
from datetime import UTC, datetime

from a2a_scorecard import ecosystem
from a2a_scorecard.batch import BatchOutcome, BatchRecord
from a2a_scorecard.dataset import RunFile, RunWriter, read_run
from a2a_scorecard.models import CheckResult, CheckStatus, TargetReport

GENERATED_AT = datetime(2026, 8, 22, 12, 0, 0, tzinfo=UTC)


def _check(
    check_id: str, title: str, status: str, weight: int = 10, details: dict | None = None
) -> dict:
    return {
        "check_id": check_id,
        "title": title,
        "status": status,
        "weight": weight,
        "evidence": "",
        "details": details or {},
    }


def _report(
    *,
    spec_generation: str = "v1",
    grade: str = "B",
    grade_withheld: str | None = None,
    results: list[dict] | None = None,
    applicable_weight: int = 80,
    max_weight: int = 100,
) -> dict:
    results = (
        results
        if results is not None
        else [_check("C001", "Endpoint reachable over HTTPS", "pass")]
    )
    return {
        "target": "https://example.invalid/should-never-appear",
        "scanned_at": "2026-08-01T00:00:00Z",
        "scanner_version": "0.3.0",
        "grading_version": "1",
        "spec_generation": spec_generation,
        "score": 80.0,
        "grade": grade,
        "grade_withheld": grade_withheld,
        "applicable_weight": applicable_weight,
        "max_weight": max_weight,
        "results": results,
    }


def _row(
    target_id: str,
    operator: str,
    *,
    outcome: str = "ok",
    report: dict | None = None,
    started_at: str = "2026-08-01T00:00:00Z",
) -> dict:
    return {
        "record_type": "target",
        "run_id": "run-20260801T000000Z",
        "target_id": target_id,
        "target": f"https://{target_id}/",
        "operator": operator,
        "provenance": None,
        "started_at": started_at,
        "elapsed_s": 0.1,
        "outcome": outcome,
        "error": None,
        "scanner_version": "0.3.0",
        "grading_version": "1",
        "spec_version": "1.0.1",
        "grading_manifest_digest": "sha256:deadbeef",
        "report": report,
    }


def _header(run_id: str = "run-20260801T000000Z") -> dict:
    return {
        "record_type": "run_start",
        "run_id": run_id,
        "scanner_version": "0.3.0",
        "grading_version": "1",
        "spec_version": "1.0.1",
        "grading_manifest_digest": "sha256:deadbeef",
    }


def _run_file(rows: list[dict], *, header: dict | None = None) -> RunFile:
    return RunFile(header=header or _header(), targets=rows, footer={"record_type": "run_end"})


# --- operator cap ------------------------------------------------------------


def test_operator_cap_caps_and_is_deterministic_under_shuffle():
    rows = [_row(f"op-a.example/t{i}", "op-a", report=_report()) for i in range(5)]
    rows.append(_row("op-b.example/t0", "op-b", report=_report()))

    shuffled_a = rows[:]
    shuffled_b = rows[:]
    random.Random(1).shuffle(shuffled_a)
    random.Random(2).shuffle(shuffled_b)

    stats_a = ecosystem.aggregate([_run_file(shuffled_a)], per_operator_cap=2)
    stats_b = ecosystem.aggregate([_run_file(shuffled_b)], per_operator_cap=2)

    assert stats_a == stats_b
    # op-a contributes at most 2 of its 5 records; op-b contributes its 1.
    assert stats_a.capped_n == 3
    assert stats_a.operators_in_capped_n == 2


def test_capped_n_and_raw_n_differ_when_operator_over_cap():
    rows = [_row(f"op-a.example/t{i}", "op-a", report=_report()) for i in range(5)]
    stats = ecosystem.aggregate([_run_file(rows)], per_operator_cap=2)

    assert stats.raw_n == 5
    assert stats.capped_n == 2
    assert stats.capped_n < stats.raw_n


# --- generations never pooled -------------------------------------------------


def test_generations_are_stratified_not_pooled():
    # v0.x: all A. v1: all F. A pooled headline would land around 50% A,
    # which is true of neither generation - this is exactly the inversion
    # ADR-0017 rule 4 exists to prevent.
    v0x_rows = [
        _row(f"v0x-{i}.example/t", f"op-v0x-{i}", report=_report(spec_generation="v0.x", grade="A"))
        for i in range(4)
    ]
    v1_rows = [
        _row(f"v1-{i}.example/t", f"op-v1-{i}", report=_report(spec_generation="v1", grade="F"))
        for i in range(4)
    ]
    stats = ecosystem.aggregate([_run_file(v0x_rows + v1_rows)], per_operator_cap=2)

    v0x_dist = stats.grade_distribution["v0.x"]
    v1_dist = stats.grade_distribution["v1"]

    assert v0x_dist["A"] == ecosystem.Ratio(4, 4, "capped v0.x scans")
    assert v0x_dist["F"] == ecosystem.Ratio(0, 4, "capped v0.x scans")
    assert v1_dist["A"] == ecosystem.Ratio(0, 4, "capped v1 scans")
    assert v1_dist["F"] == ecosystem.Ratio(4, 4, "capped v1 scans")

    # A pooled distribution would show 4/8 A - stratification means neither
    # generation's own denominator is 8.
    assert v0x_dist["A"].denominator == 4
    assert v1_dist["F"].denominator == 4


def test_ng_never_lands_in_a_failure_bucket():
    rows = [
        _row("g1.example/t", "op-g1", report=_report(grade="NG", grade_withheld="coverage")),
        _row("g2.example/t", "op-g2", report=_report(grade="F")),
    ]
    stats = ecosystem.aggregate([_run_file(rows)], per_operator_cap=2)
    dist = stats.grade_distribution["v1"]

    assert dist["NG"].numerator == 1
    assert dist["F"].numerator == 1
    # NG must not have been folded into F (or any other letter).
    assert sum(dist[g].numerator for g in ("A", "B", "C", "D", "F")) == 1


# --- absences ------------------------------------------------------------------


def test_absences_are_not_counted_as_scanned():
    rows = [
        _row("ok.example/t", "op-ok", outcome="ok", report=_report()),
        _row("excl.example/t", "op-excl", outcome=BatchOutcome.EXCLUDED.value, report=None),
        _row("thr.example/t", "op-thr", outcome=BatchOutcome.THROTTLED.value, report=None),
        _row("skip.example/t", "op-skip", outcome=BatchOutcome.SKIPPED_RECENT.value, report=None),
        _row("err.example/t", "op-err", outcome=BatchOutcome.ERROR.value, report=None),
    ]
    stats = ecosystem.aggregate([_run_file(rows)], per_operator_cap=2)

    assert stats.capped_n == 5
    assert stats.scanned_n == 1
    assert stats.reachable.denominator == 1
    assert stats.scannable.denominator == 1
    assert stats.outcome_counts[BatchOutcome.EXCLUDED.value].numerator == 1
    assert stats.outcome_counts[BatchOutcome.THROTTLED.value].numerator == 1
    assert stats.outcome_counts[BatchOutcome.SKIPPED_RECENT.value].numerator == 1
    assert stats.outcome_counts[BatchOutcome.ERROR.value].numerator == 1
    assert stats.outcome_counts[BatchOutcome.OK.value].numerator == 1
    for ratio in stats.outcome_counts.values():
        assert ratio.denominator == 5


# --- rendering -------------------------------------------------------------


def _sample_stats():
    rows = [
        _row(
            "a.example/t",
            "op-a",
            report=_report(
                spec_generation="v1",
                grade="B",
                results=[
                    _check("C001", "Endpoint reachable over HTTPS", "pass"),
                    _check("C011", "Agent Card is valid JSON", "pass"),
                    _check("C010", "Agent Card served at well-known URI", "pass"),
                    _check("C032", "TLS configuration and certificate posture", "pass"),
                    _check("C020", "Agent answers a spec-conformant SendMessage", "pass"),
                ],
            ),
        ),
        _row(
            "b.example/t",
            "op-b",
            report=_report(
                spec_generation="v0.x",
                grade="A",
                results=[
                    _check("C001", "Endpoint reachable over HTTPS", "warn"),
                    _check("C011", "Agent Card is valid JSON", "pass"),
                    _check("C010", "Agent Card served at well-known URI", "warn"),
                    _check(
                        "C020",
                        "Agent answers a spec-conformant SendMessage",
                        "fail",
                        details={"auth_required": True},
                    ),
                ],
            ),
        ),
    ]
    return ecosystem.aggregate([_run_file(rows)], per_operator_cap=2)


def test_render_markdown_is_deterministic():
    stats = _sample_stats()
    provenance = ecosystem.Provenance.from_run_files([_run_file([])])
    text_a = ecosystem.render_markdown(stats, generated_at=GENERATED_AT, provenance=provenance)
    text_b = ecosystem.render_markdown(stats, generated_at=GENERATED_AT, provenance=provenance)
    assert text_a == text_b


def test_render_markdown_never_names_operator_or_target():
    distinctive_operator = "definitely-not-a-public-operator-llc"
    distinctive_host = "sekrit-operator-xyz.example.com"
    rows = [
        _row(
            f"{distinctive_host}/well-known",
            distinctive_operator,
            report=_report(),
        )
    ]
    stats = ecosystem.aggregate([_run_file(rows)], per_operator_cap=2)
    provenance = ecosystem.Provenance.from_run_files([_run_file(rows)])
    text = ecosystem.render_markdown(stats, generated_at=GENERATED_AT, provenance=provenance)

    assert distinctive_operator not in text
    assert distinctive_host not in text
    # The fixture report's own `target` field must not leak either.
    assert "example.invalid/should-never-appear" not in text


def test_render_markdown_never_prints_a_bare_percentage():
    stats = _sample_stats()
    provenance = ecosystem.Provenance.from_run_files([_run_file([])])
    text = ecosystem.render_markdown(stats, generated_at=GENERATED_AT, provenance=provenance)

    # Every occurrence of "%" must appear inside the "n/d (x.y%) of <scope>"
    # idiom that Ratio.render() always produces - i.e. it is structurally
    # impossible for a percentage to be printed without its numerator and
    # denominator on the same line. A regex scan (rather than inspecting
    # Ratio's methods) is the stronger guarantee here because it checks
    # what actually got written to the file, not just what the type allows.
    ratio_pattern = re.compile(r"\d+/\d+ \([0-9.]+%\) of ")
    for line in text.splitlines():
        if "%" in line:
            assert ratio_pattern.search(line), f"bare percentage in line: {line!r}"


# --- integration: real RunWriter/read_run round trip --------------------------


def test_write_report_round_trips_through_runwriter(tmp_path):
    run_path = tmp_path / "run-20260801T000000Z.jsonl"
    report = TargetReport(
        target="https://round-trip-operator.example/",
        scanned_at="2026-08-01T00:00:00Z",
        scanner_version="0.3.0",
        grading_version="1",
        spec_generation="v1",
        results=[CheckResult("C001", "Endpoint reachable over HTTPS", CheckStatus.PASS, 10)],
        score=100.0,
        grade="B",
        applicable_weight=10,
        max_weight=10,
    )
    with RunWriter(run_path, run_id="run-20260801T000000Z", now=GENERATED_AT) as writer:
        writer(
            BatchRecord(
                target_id="round-trip-operator.example/",
                target_url="https://round-trip-operator.example/",
                operator="round-trip-operator",
                outcome=BatchOutcome.OK,
                report=report,
                started_at=0.0,
                finished_at=1.0,
            )
        )

    run_file = read_run(run_path)
    assert run_file.complete

    out_path = tmp_path / "ECOSYSTEM.md"
    stats = ecosystem.write_report(
        [run_file], out_path, per_operator_cap=2, generated_at=GENERATED_AT
    )

    assert stats.scanned_n == 1
    text = out_path.read_text(encoding="utf-8")
    assert "round-trip-operator" not in text
    assert "run-20260801T000000Z" in text
