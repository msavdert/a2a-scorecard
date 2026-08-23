import pytest

from a2a_scorecard import grading
from a2a_scorecard.grading import NG, grade, grade_rank, graded_result, score, withheld_message
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


# --- ADR-0017: letter-withholding rules ------------------------------------
#
# These tests build CheckResult lists with hand-picked integer weights so
# coverage (applicable_weight / max_weight) lands on an exact fraction,
# including values either side of the 0.60 and 0.75 thresholds that are not
# reachable with small integer weights (e.g. 0.5999). A total weight of
# 10000 keeps every boundary an exact division.


def _probed(status: CheckStatus, weight: int, check_id: str = "C020") -> CheckResult:
    return CheckResult(check_id=check_id, title="message handling", status=status, weight=weight)


def _padding(
    weight: int, status: CheckStatus = CheckStatus.SKIP, check_id: str = "C013"
) -> CheckResult:
    return CheckResult(check_id=check_id, title="padding", status=status, weight=weight)


def test_coverage_just_below_floor_is_ng() -> None:
    # coverage = 5999 / 10000 = 0.5999, message handling probed (PASS), but
    # rule 1 (coverage floor) still withholds the letter.
    results = [_probed(CheckStatus.PASS, 5999), _padding(4001)]
    assert graded_result(results) == (NG, "coverage")


def test_coverage_exactly_at_floor_is_not_withheld_by_rule1() -> None:
    # coverage = 6000 / 10000 = 0.60 exactly: the floor is "< 0.60", so this
    # is not withheld. WARN keeps the score out of the A band (score 50,
    # grade D) so this test isolates rule 1's boundary from rule 3.
    results = [_probed(CheckStatus.WARN, 6000), _padding(4000)]
    assert graded_result(results) == ("D", None)


def test_coverage_just_above_floor_is_not_withheld() -> None:
    # coverage = 6001 / 10000 = 0.6001.
    results = [_probed(CheckStatus.WARN, 6001), _padding(3999)]
    assert graded_result(results) == ("D", None)


def test_a_band_just_below_coverage_floor_is_demoted_to_b() -> None:
    # coverage = 6999 / 10000 = 0.6999, score 100 (A band by score alone),
    # but rule 3 demotes to B because coverage is below the 0.70 floor.
    results = [_probed(CheckStatus.PASS, 6999), _padding(3001)]
    assert graded_result(results) == ("B", None)


def test_a_band_exactly_at_coverage_floor_stays_a() -> None:
    # coverage = 7000 / 10000 = 0.70 exactly: ">= 0.70" is inclusive, so
    # this stays A.
    results = [_probed(CheckStatus.PASS, 7000), _padding(3000)]
    assert graded_result(results) == ("A", None)


def test_a_band_just_above_coverage_floor_stays_a() -> None:
    # coverage = 7001 / 10000 = 0.7001.
    results = [_probed(CheckStatus.PASS, 7001), _padding(2999)]
    assert graded_result(results) == ("A", None)


def test_message_handling_probed_via_c023_counts() -> None:
    # Rule 2 accepts either C020 or C023; a REST-only target that got a
    # real result from C023 alone must not be withheld as unprobed.
    results = [_probed(CheckStatus.PASS, 7500, check_id="C023"), _padding(2500)]
    assert graded_result(results) == ("A", None)


def test_message_handling_never_probed_is_ng_even_at_high_coverage() -> None:
    # The case that did NOT occur in the census and is the likeliest
    # regression: high coverage and a score that would otherwise be A, but
    # C020/C023 only ever produced SKIP - never a real result - so rule 2
    # withholds the letter instead of awarding A. SKIP (not BLOCKED) is the
    # genuine "never probed" shape: BLOCKED now counts as a conclusion
    # (see test_message_handling_blocked_counts_as_probed below), so it can
    # no longer stand in for this case.
    results = [
        CheckResult(check_id="C010", title="card present", status=CheckStatus.PASS, weight=9500),
        _probed(CheckStatus.SKIP, 500),
    ]
    assert score(results) == 100.0
    assert graded_result(results) == (NG, "unprobed")


def test_message_handling_blocked_counts_as_probed() -> None:
    # ADR-0017 amendment: BLOCKED is a conclusion (a dependency of the
    # probe failed - no card, unparseable card, unreachable host - which is
    # a finding about the target), not an absence of measurement. Same
    # shape as the SKIP case above (C020 never got a real PASS/WARN/FAIL),
    # but BLOCKED must NOT withhold the letter. Contrast the two directly:
    # SKIP on C020 -> unprobed NG; BLOCKED on C020 -> a real letter.
    results = [
        CheckResult(check_id="C010", title="card present", status=CheckStatus.PASS, weight=9500),
        _probed(CheckStatus.BLOCKED, 500),
    ]
    assert score(results) == 95.0
    assert graded_result(results) == ("A", None)


def test_all_blocked_dead_target_shape_grades_not_withheld() -> None:
    # The exact shape a dead/unreachable target produces in a real scan
    # (scan.py): the reachability check FAILs and every downstream check -
    # including C020/C023 - is reported BLOCKED, never SKIP. This is the
    # shape the original (pre-amendment) unit tests never built, because
    # they constructed check lists by hand instead of running a scan - the
    # defect only surfaced once graded_result() was wired into scan.py.
    # Nothing here is SKIP, so coverage is 1.0 and rule 1 does not apply;
    # C020 is BLOCKED so rule 2 counts it as probed. The result must be a
    # real letter (F, since every weight earned 0.0), not NG.
    results = [
        CheckResult(check_id="C001", title="reachability", status=CheckStatus.FAIL, weight=5000),
        CheckResult(check_id="C010", title="card present", status=CheckStatus.BLOCKED, weight=2000),
        _probed(CheckStatus.BLOCKED, 3000),
    ]
    assert score(results) == 0.0
    letter, withheld = graded_result(results)
    assert letter == "F"
    assert withheld is None


def test_message_handling_skip_or_error_also_counts_as_unprobed() -> None:
    results = [
        CheckResult(check_id="C010", title="card present", status=CheckStatus.PASS, weight=8000),
        _probed(CheckStatus.SKIP, 1000),
        _probed(CheckStatus.ERROR, 1000, check_id="C023"),
    ]
    assert graded_result(results) == (NG, "unprobed")


def test_message_handling_absent_entirely_also_counts_as_unprobed() -> None:
    results = [
        CheckResult(check_id="C010", title="card present", status=CheckStatus.PASS, weight=8000),
    ]
    assert graded_result(results) == (NG, "unprobed")


def test_rule1_takes_precedence_over_rule2() -> None:
    # Both the coverage floor (applicable 4000/10000 = 0.40) and the
    # unprobed rule (C020 only ever BLOCKED) apply here. ADR-0017 states
    # rule 1 wins; this must be stable and not depend on iteration order.
    results = [
        CheckResult(check_id="C010", title="card present", status=CheckStatus.PASS, weight=3000),
        _probed(CheckStatus.BLOCKED, 1000),
        _padding(6000),
    ]
    assert graded_result(results) == (NG, "coverage")


def test_ng_is_not_a_letter() -> None:
    assert NG not in grading._LETTER_ORDER


def test_grade_rank_orders_real_letters() -> None:
    assert grade_rank("A") < grade_rank("B") < grade_rank("C") < grade_rank("D") < grade_rank("F")


def test_grade_rank_rejects_ng() -> None:
    with pytest.raises(ValueError):
        grade_rank(NG)


def test_withheld_message_text_coverage() -> None:
    assert withheld_message("coverage", 0.5625) == "NG (not graded: coverage 0.56 below 0.60 floor)"


def test_withheld_message_text_unprobed() -> None:
    assert withheld_message("unprobed", 0.875) == "NG (not graded: message handling never probed)"


def test_withheld_message_rejects_unknown_reason() -> None:
    with pytest.raises(ValueError):
        withheld_message("bogus", 0.5)
