"""Score and grade math. Semantics are fixed by ADR-0005 and amended by
ADR-0017; change them only with a new ADR and updated tests in the same
commit."""

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

# "Not Graded": returned in place of a letter when ADR-0017 withholds one.
# NG is explicitly NOT a failing grade. It is deliberately excluded from
# _LETTER_ORDER below so it can never sort, compare, or aggregate as if it
# were a letter - see grade_rank().
NG = "NG"

_LETTER_ORDER = ["A", "B", "C", "D", "F"]  # NG is not a letter; kept out on purpose.

# --- ADR-0017 thresholds. Pinned to GRADING_VERSION: they may only change
# together with a superseding ADR and a GRADING_VERSION bump. ---

# Rule 1 (coverage floor): below this fraction of applicable_weight /
# max_weight, no letter is emitted at all.
COVERAGE_FLOOR = 0.60

# Rule 3 (A band floor): the A band additionally requires at least this
# coverage; an A-band score below it is reported as B instead. Set to 0.70
# rather than the v1 median of 0.75 the census suggested: a perfect,
# minimal v1 agent over HTTPS lands on exactly 0.75, so a 0.75 floor would
# put every such agent one newly added check away from silently losing its
# A. On the census sample 0.70 and 0.75 select the identical set of A
# grades, so the margin costs nothing (ADR-0017).
A_BAND_COVERAGE_FLOOR = 0.70

# Rule 2 (message handling must have been probed): unlike rules 1 and 3,
# this rule is necessarily expressed in terms of specific check ids, since
# "was message handling probed" is defined by which checks exist to probe
# it (C020 JSON-RPC SendMessage, C023 REST binding). Update this set when a
# new message-binding probe check is added.
MESSAGE_HANDLING_CHECKS = frozenset({"C020", "C023"})

# Statuses that count as "we reached a conclusion about message handling",
# as opposed to never having probed at all (SKIP, ERROR, or simply absent).
#
# BLOCKED is deliberately included. It means a dependency of the probe
# failed - no card, unparseable card, unreachable host - which is a finding
# about the target, and a damning one, not an absence of measurement. Left
# out, an unreachable endpoint scored NG ("not graded") instead of F, which
# is the exact opposite of the truth: a dead endpoint is the most
# conclusive measurement there is (ADR-0017).
_PROBED_STATUSES = frozenset(
    {CheckStatus.PASS, CheckStatus.WARN, CheckStatus.FAIL, CheckStatus.BLOCKED}
)


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
    """Letter band for a bare score. Does not apply ADR-0017's withholding
    rules - it only knows a number, not coverage or which checks ran. Use
    graded_result() to get the full, ADR-0017-compliant letter (or NG)."""
    for threshold, letter in _BANDS:
        if value >= threshold:
            return letter
    return "F"


def grade_rank(letter: str) -> int:
    """Sortable rank for a letter grade, best (A) first.

    Raises ValueError for NG: NG is not a failing grade and must never be
    ordered, compared, or aggregated alongside real letters (ADR-0017).
    Callers that need to bucket NG separately should check for it before
    calling this, not catch the exception as a sort key.
    """
    if letter == NG:
        raise ValueError('"NG" has no rank: it is a withheld grade, not a grade')
    return _LETTER_ORDER.index(letter)


def _message_handling_probed(results: list[CheckResult]) -> bool:
    """ADR-0017 rule 2: True if C020 or C023 produced a real result."""
    return any(
        r.check_id in MESSAGE_HANDLING_CHECKS and r.status in _PROBED_STATUSES for r in results
    )


def coverage(results: list[CheckResult]) -> float:
    """Fraction of max_weight the score was actually computed over."""
    total = max_weight(results)
    if total == 0:
        return 0.0
    return applicable_weight(results) / total


def graded_result(results: list[CheckResult]) -> tuple[str, str | None]:
    """ADR-0017's full grading decision: (letter_or_NG, grade_withheld).

    grade_withheld is None for a real letter, otherwise "coverage" or
    "unprobed". Rule precedence when both the coverage floor and the
    unprobed rule apply: rule 1 (coverage) wins. This is a deliberate,
    fixed choice - not incidental to dict/list iteration order - so the
    reason a report carries is stable and reproducible: the coverage floor
    is checked first, unconditionally, before message-handling is even
    inspected.
    """
    cov = coverage(results)
    if cov < COVERAGE_FLOOR:
        return NG, "coverage"
    if not _message_handling_probed(results):
        return NG, "unprobed"

    letter = grade(score(results))
    if letter == "A" and cov < A_BAND_COVERAGE_FLOOR:
        letter = "B"
    return letter, None


def withheld_message(grade_withheld: str, cov: float) -> str:
    """Human-readable explanation for a withheld grade (ADR-0017), for the
    text report. `cov` is the coverage fraction (applicable_weight /
    max_weight)."""
    if grade_withheld == "coverage":
        return f"NG (not graded: coverage {cov:.2f} below {COVERAGE_FLOOR:.2f} floor)"
    if grade_withheld == "unprobed":
        return "NG (not graded: message handling never probed)"
    raise ValueError(f"unknown grade_withheld reason: {grade_withheld!r}")
