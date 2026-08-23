import json

from a2a_scorecard.cli import _render_text, main
from a2a_scorecard.grading import NG
from a2a_scorecard.models import TargetReport


def test_cli_json_output(fake_agent, capsys) -> None:
    url = fake_agent("compliant")
    exit_code = main(["scan", url, "--json", "--allow-http"])
    assert exit_code == 0
    reports = json.loads(capsys.readouterr().out)
    assert len(reports) == 1
    assert reports[0]["target"] == url
    # ADR-0017 rule 3: the "compliant" fixture scores 100 but its coverage
    # (110/160 = 0.6875) is below the 0.70 A-band floor, so the grade is
    # held at B (see tests/test_scan.py for the coverage arithmetic).
    assert reports[0]["grade"] == "B"


def test_cli_text_output(fake_agent, capsys) -> None:
    url = fake_agent("no-card")
    exit_code = main(["scan", url, "--allow-http"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "grade: F" in out
    assert "C010" in out


def _ng_report(grade_withheld: str) -> TargetReport:
    return TargetReport(
        target="https://example.test",
        scanned_at="2026-08-22T00:00:00Z",
        scanner_version="0.0.0",
        grading_version="1",
        spec_generation="v1",
        results=[],
        score=56.0,
        grade=NG,
        applicable_weight=90,
        max_weight=160,
        grade_withheld=grade_withheld,
    )


def test_render_text_ng_coverage_reason() -> None:
    # ADR-0017: 90 / 160 = 0.5625, rounded to two decimals as "0.56".
    out = _render_text(_ng_report("coverage"))
    assert "NG (not graded: coverage 0.56 below 0.60 floor)" in out


def test_render_text_ng_unprobed_reason() -> None:
    out = _render_text(_ng_report("unprobed"))
    assert "NG (not graded: message handling never probed)" in out


def test_render_text_normal_letter_is_unaffected() -> None:
    report = _ng_report("coverage")
    report.grade = "B"
    report.grade_withheld = None
    out = _render_text(report)
    assert "grade: B" in out
    assert "NG" not in out
