"""CheckResult.__post_init__ evidence sanitization: ANSI/control-character
injection and unbounded evidence length are both cli.py's problem to render
safely and this dataclass's problem to prevent (single choke point, so every
check gets the guard for free)."""

from __future__ import annotations

from a2a_scorecard.grading import NG
from a2a_scorecard.models import CheckResult, CheckStatus, TargetReport


def _make(evidence: str) -> CheckResult:
    return CheckResult(
        check_id="C000",
        title="fixture check",
        status=CheckStatus.PASS,
        weight=1,
        evidence=evidence,
    )


def test_long_evidence_is_truncated() -> None:
    result = _make("x" * 1000)
    assert len(result.evidence) == 500 + len("...")
    assert result.evidence.endswith("...")
    assert result.evidence.startswith("x" * 500)


def test_short_evidence_is_untouched() -> None:
    result = _make("all good")
    assert result.evidence == "all good"


def test_ansi_escape_is_stripped() -> None:
    result = _make("\x1b[31mred text\x1b[0m")
    assert "\x1b" not in result.evidence
    assert result.evidence == " [31mred text [0m"


def test_c0_and_c1_control_characters_are_replaced() -> None:
    result = _make("a\x00b\x07c\x9fd")
    assert result.evidence == "a b c d"


def test_newline_and_tab_are_preserved() -> None:
    result = _make("line one\nline two\tindented")
    assert result.evidence == "line one\nline two\tindented"


def _make_report(**overrides: object) -> TargetReport:
    defaults: dict[str, object] = {
        "target": "https://example.test",
        "scanned_at": "2026-08-22T00:00:00Z",
        "scanner_version": "0.0.0",
        "grading_version": "1",
        "spec_generation": "v1",
        "results": [],
        "score": 95.0,
        "grade": "A",
        "applicable_weight": 100,
        "max_weight": 100,
    }
    defaults.update(overrides)
    return TargetReport(**defaults)  # type: ignore[arg-type]


def test_grade_withheld_defaults_to_none() -> None:
    report = _make_report()
    assert report.grade_withheld is None
    assert report.to_dict()["grade_withheld"] is None


def test_ng_grade_round_trips_through_to_dict() -> None:
    # ADR-0017: a withheld grade must survive to_dict() as "NG" plus its
    # reason, not silently drop back to a letter or lose the reason.
    report = _make_report(grade=NG, grade_withheld="coverage")
    data = report.to_dict()
    assert data["grade"] == "NG"
    assert data["grade_withheld"] == "coverage"

    report_unprobed = _make_report(grade=NG, grade_withheld="unprobed")
    assert report_unprobed.to_dict()["grade_withheld"] == "unprobed"
