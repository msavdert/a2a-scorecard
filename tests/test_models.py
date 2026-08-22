"""CheckResult.__post_init__ evidence sanitization: ANSI/control-character
injection and unbounded evidence length are both cli.py's problem to render
safely and this dataclass's problem to prevent (single choke point, so every
check gets the guard for free)."""

from __future__ import annotations

from a2a_scorecard.models import CheckResult, CheckStatus


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
