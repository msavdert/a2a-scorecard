"""Score and grade math. Semantics are fixed by ADR-0005; change them only
with a new ADR and updated tests in the same commit."""

from __future__ import annotations

from a2a_scorecard.models import CheckResult, CheckStatus

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
