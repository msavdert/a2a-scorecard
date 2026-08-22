"""Score and grade math. Semantics are fixed by ADR-0005; change them only
with a new ADR and updated tests in the same commit."""

from __future__ import annotations

from a2a_scorecard.models import CheckResult, CheckStatus

# Grading methodology version (ADR-0011): the check set, weights, earned
# mapping and letter bands a report was graded under. Increments only when
# a released grade for an unchanged target could change; stays "1" until
# the first public dataset freezes it.
GRADING_VERSION = "1"

# Fraction of a check's weight earned per status. SKIP is excluded from
# the denominator entirely; everything else counts against it.
_EARNED = {
    CheckStatus.PASS: 1.0,
    CheckStatus.WARN: 0.5,
    CheckStatus.FAIL: 0.0,
    CheckStatus.BLOCKED: 0.0,
    CheckStatus.ERROR: 0.0,
}

_BANDS = [(90.0, "A"), (75.0, "B"), (60.0, "C"), (40.0, "D")]


def applicable_weight(results: list[CheckResult]) -> int:
    """Weight the score was actually computed over: non-SKIP results only.

    Reported next to max_weight as probe coverage (ADR-0015); does not
    affect the score or grade.
    """
    return sum(r.weight for r in results if r.status is not CheckStatus.SKIP)


def max_weight(results: list[CheckResult]) -> int:
    """Total weight of every check that ran or was skipped in this scan."""
    return sum(r.weight for r in results)


def score(results: list[CheckResult]) -> float:
    applicable = [r for r in results if r.status is not CheckStatus.SKIP]
    total = sum(r.weight for r in applicable)
    if total == 0:
        return 0.0
    earned = sum(r.weight * _EARNED[r.status] for r in applicable)
    return round(100.0 * earned / total, 1)


def grade(value: float) -> str:
    for threshold, letter in _BANDS:
        if value >= threshold:
            return letter
    return "F"
