"""Unit tests for C031 defensive paths not worth a dedicated fake-agent mode:
these exercise `AgentCardSignatureStructure.run` directly against a
hand-built `ProbeContext`, since C031 reads only `ctx.card` and never
touches the network (ADR-0009)."""

from __future__ import annotations

import base64

import httpx

from a2a_scorecard.checks.base import ProbeContext
from a2a_scorecard.checks.signature import AgentCardSignatureStructure
from a2a_scorecard.config import Settings
from a2a_scorecard.models import CheckStatus


def _ctx(card: dict) -> ProbeContext:
    ctx = ProbeContext("http://example.invalid", httpx.Client(), Settings(allow_http=True))
    ctx.card = card
    ctx.spec_generation = "v1"
    return ctx


def test_entry_not_an_object_fails() -> None:
    ctx = _ctx({"signatures": ["not-an-object"]})
    result = AgentCardSignatureStructure().run(ctx)
    assert result.status is CheckStatus.FAIL
    assert "entry 0 is not an object" in result.evidence


def test_protected_decodes_to_non_utf8_bytes_fails() -> None:
    # base64url-decodable, but the resulting bytes (\x80ABC) are not valid
    # UTF-8: json.loads must not be allowed to raise UnicodeDecodeError past
    # the check and turn a structural FAIL into an ERROR (ADR-0009).
    ctx = _ctx(
        {
            "signatures": [
                {
                    "protected": "gEFCQw",
                    "signature": base64.urlsafe_b64encode(b"sig").decode().rstrip("="),
                }
            ]
        }
    )
    result = AgentCardSignatureStructure().run(ctx)
    assert result.status is CheckStatus.FAIL
    assert "does not decode to valid JSON" in result.evidence


def test_protected_with_non_alphabet_characters_fails() -> None:
    # "!" is not part of the base64url alphabet. The prior implementation
    # (base64.urlsafe_b64decode) silently dropped such characters instead of
    # rejecting them; the padded length here is a multiple of 4, so it would
    # have "decoded" without error.
    ctx = _ctx(
        {
            "signatures": [
                {
                    "protected": "not_actually_base64!!",
                    "signature": base64.urlsafe_b64encode(b"sig").decode().rstrip("="),
                }
            ]
        }
    )
    result = AgentCardSignatureStructure().run(ctx)
    assert result.status is CheckStatus.FAIL
    assert "'protected' is not base64url-decodable" in result.evidence


def test_protected_decodes_to_non_object_json_fails() -> None:
    protected = base64.urlsafe_b64encode(b'"just a string"').decode().rstrip("=")
    ctx = _ctx(
        {
            "signatures": [
                {
                    "protected": protected,
                    "signature": base64.urlsafe_b64encode(b"sig").decode().rstrip("="),
                }
            ]
        }
    )
    result = AgentCardSignatureStructure().run(ctx)
    assert result.status is CheckStatus.FAIL
    assert "does not decode to a JSON object" in result.evidence
