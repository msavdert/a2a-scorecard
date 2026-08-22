from a2a_scorecard.grading import grade, score
from a2a_scorecard.models import CheckResult, CheckStatus


def result(status: CheckStatus, weight: int = 10) -> CheckResult:
    return CheckResult(check_id="CX", title="x", status=status, weight=weight)


def test_all_pass_is_100() -> None:
    assert score([result(CheckStatus.PASS), result(CheckStatus.PASS)]) == 100.0


def test_warn_earns_half_weight() -> None:
    assert score([result(CheckStatus.PASS), result(CheckStatus.WARN)]) == 75.0


def test_blocked_counts_in_denominator() -> None:
    assert score([result(CheckStatus.PASS), result(CheckStatus.BLOCKED)]) == 50.0


def test_skip_is_excluded_entirely() -> None:
    assert score([result(CheckStatus.PASS), result(CheckStatus.SKIP)]) == 100.0


def test_error_earns_nothing() -> None:
    assert score([result(CheckStatus.ERROR)]) == 0.0


def test_no_applicable_checks_scores_zero() -> None:
    assert score([result(CheckStatus.SKIP)]) == 0.0


def test_grade_bands() -> None:
    assert grade(100.0) == "A"
    assert grade(90.0) == "A"
    assert grade(89.9) == "B"
    assert grade(75.0) == "B"
    assert grade(60.0) == "C"
    assert grade(40.0) == "D"
    assert grade(39.9) == "F"
