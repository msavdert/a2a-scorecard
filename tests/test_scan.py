from a2a_scorecard.config import Settings
from a2a_scorecard.models import CheckResult, CheckStatus, TargetReport
from a2a_scorecard.scan import run_scan

SETTINGS = Settings(allow_http=True)


def by_id(report: TargetReport) -> dict[str, CheckResult]:
    return {r.check_id: r for r in report.results}


def test_compliant_agent_grades_a(fake_agent) -> None:
    report = run_scan(fake_agent("compliant"), SETTINGS)
    results = by_id(report)
    for check_id in ("C001", "C010", "C011", "C012", "C013", "C020", "C021"):
        assert results[check_id].status is CheckStatus.PASS, (
            f"{check_id}: {results[check_id].evidence}"
        )
    assert report.spec_generation == "v1"
    assert report.score == 100.0
    assert report.grade == "A"


def test_missing_card_blocks_downstream(fake_agent) -> None:
    report = run_scan(fake_agent("no-card"), SETTINGS)
    results = by_id(report)
    assert results["C010"].status is CheckStatus.FAIL
    for check_id in ("C011", "C012", "C013", "C020", "C021"):
        assert results[check_id].status is CheckStatus.BLOCKED
    assert report.grade == "F"


def test_unparseable_card_fails_parse_check(fake_agent) -> None:
    report = run_scan(fake_agent("bad-json"), SETTINGS)
    results = by_id(report)
    assert results["C010"].status is CheckStatus.PASS
    assert results["C011"].status is CheckStatus.FAIL
    assert results["C020"].status is CheckStatus.BLOCKED


def test_schema_invalid_card_still_pings(fake_agent) -> None:
    report = run_scan(fake_agent("invalid-card"), SETTINGS)
    results = by_id(report)
    assert results["C012"].status is CheckStatus.FAIL
    assert results["C020"].status is CheckStatus.PASS
    assert report.grade == "B"


def test_card_without_protocol_endpoint(fake_agent) -> None:
    report = run_scan(fake_agent("card-only"), SETTINGS)
    results = by_id(report)
    assert results["C012"].status is CheckStatus.PASS
    assert results["C020"].status is CheckStatus.FAIL
    assert results["C021"].status is CheckStatus.BLOCKED
    assert report.grade == "C"


def test_unreachable_target_fails_cleanly() -> None:
    # Localhost discard port: refused immediately, no traffic leaves the machine.
    report = run_scan("http://127.0.0.1:9", Settings(allow_http=True, timeout_s=0.5))
    results = by_id(report)
    assert results["C001"].status is CheckStatus.FAIL
    assert report.grade == "F"
