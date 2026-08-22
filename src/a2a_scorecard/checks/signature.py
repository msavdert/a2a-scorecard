"""Stage 3: Agent Card JWS signature structural check (C031).

Inspects only the already-fetched Agent Card; sends no network traffic of
its own, so it fits inside SCANNING-POLICY without amendment (ADR-0009).

Field names below come from the vendored v1 schema
(``src/a2a_scorecard/vendor/a2a-v1.0.1.json``), definition ``Agent Card
Signature``: an array of objects with ``protected`` (base64url-encoded JSON
object, required per the spec text), ``signature`` (base64url, required),
and an optional unprotected ``header`` object (RFC 7515 JWS JSON
serialization).

Scope is structural only (ADR-0009): cryptographic verification of the
signature bytes is explicitly out of scope and deferred to a later check.
This check only decodes ``protected`` and inspects the resulting JWS header
for ``alg`` and key-resolution hints.
"""

from __future__ import annotations

import base64
import binascii
import json
from typing import Any

from a2a_scorecard.checks.base import Check, ProbeContext
from a2a_scorecard.models import CheckResult, CheckStatus

# RFC 7518 asymmetric signature algs plus EdDSA (RFC 8037). Deliberately
# excludes ES256K: it is not part of the RFC 7518 / EdDSA registry this
# check is scoped to (ADR-0009).
_ASYMMETRIC_ALGS = frozenset(
    {
        "RS256",
        "RS384",
        "RS512",
        "PS256",
        "PS384",
        "PS512",
        "ES256",
        "ES384",
        "ES512",
        "EdDSA",
    }
)

_SYMMETRIC_ALGS = frozenset({"HS256", "HS384", "HS512"})

_KEY_HINT_FIELDS = ("jwks", "jku", "kid", "x5c", "x5u")


def _b64url_decode(value: str) -> bytes | None:
    padded = value + "=" * (-len(value) % 4)
    try:
        # base64.urlsafe_b64decode silently ignores non-alphabet characters;
        # b64decode(..., validate=True) rejects them instead (ADR-0009 wants
        # a structural FAIL for garbage input, not a false-positive decode).
        return base64.b64decode(padded.encode("ascii"), altchars=b"-_", validate=True)
    except (binascii.Error, ValueError):
        return None


class AgentCardSignatureStructure(Check):
    """Checks that any `signatures` entries on the Agent Card are
    structurally valid JWS: base64url-decodable, with a JSON object protected
    header, an `alg`, and (as a WARN-level distinction) an asymmetric alg and
    a key-resolution hint (ADR-0009). Signing is optional, so an unsigned
    card SKIPs rather than losing points."""

    check_id = "C031"
    title = "Agent Card signatures are structurally valid JWS"
    stage = 3
    weight = 10
    requires = ("C011",)

    def run(self, ctx: ProbeContext) -> CheckResult:
        assert ctx.card is not None
        if ctx.spec_generation != "v1":
            return self.result(
                CheckStatus.SKIP,
                evidence=f"card generation is '{ctx.spec_generation}', not v1; "
                "the JWS structural rules are written against the v1 card shape",
            )
        card = ctx.card
        raw_signatures: Any = card.get("signatures")
        if not raw_signatures:
            return self.result(
                CheckStatus.SKIP, evidence="card declares no signatures; signing is optional"
            )

        if not isinstance(raw_signatures, list):
            problems = ["signatures is not a list"]
            return self.result(
                CheckStatus.FAIL,
                evidence="; ".join(problems),
                details={"problems": problems},
            )
        signatures: list[Any] = raw_signatures

        fail_problems: list[str] = []
        warn_problems: list[str] = []

        for index, entry in enumerate(signatures):
            if not isinstance(entry, dict):
                fail_problems.append(f"entry {index} is not an object")
                continue
            entry_fail, entry_warn = _check_entry(index, entry)
            fail_problems.extend(entry_fail)
            warn_problems.extend(entry_warn)

        details: dict[str, Any] = {"entry_count": len(signatures)}
        if fail_problems:
            details["problems"] = fail_problems
            return self.result(CheckStatus.FAIL, evidence="; ".join(fail_problems), details=details)
        if warn_problems:
            details["problems"] = warn_problems
            return self.result(CheckStatus.WARN, evidence="; ".join(warn_problems), details=details)
        return self.result(
            CheckStatus.PASS,
            evidence=f"{len(signatures)} signature(s), all structurally valid asymmetric JWS",
            details=details,
        )


def _check_entry(index: int, entry: dict[str, Any]) -> tuple[list[str], list[str]]:
    fail: list[str] = []
    warn: list[str] = []

    protected = entry.get("protected")
    signature = entry.get("signature")

    if not isinstance(protected, str) or not protected:
        fail.append(f"entry {index}: 'protected' missing, empty, or not a string")
        return fail, warn
    if not isinstance(signature, str) or not signature:
        fail.append(f"entry {index}: 'signature' missing, empty, or not a string")
        return fail, warn

    protected_bytes = _b64url_decode(protected)
    if protected_bytes is None:
        fail.append(f"entry {index}: 'protected' is not base64url-decodable")
        return fail, warn
    if _b64url_decode(signature) is None:
        fail.append(f"entry {index}: 'signature' is not base64url-decodable")
        return fail, warn

    try:
        protected_json = json.loads(protected_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError):
        fail.append(f"entry {index}: 'protected' does not decode to valid JSON")
        return fail, warn
    if not isinstance(protected_json, dict):
        fail.append(f"entry {index}: 'protected' does not decode to a JSON object")
        return fail, warn

    alg = protected_json.get("alg")
    if not alg or not isinstance(alg, str):
        fail.append(f"entry {index}: protected header has no 'alg'")
        return fail, warn
    if alg == "none":
        fail.append(f"entry {index}: alg is 'none'")
        return fail, warn

    unprotected = entry.get("header")
    if not isinstance(unprotected, dict):
        unprotected = {}

    if alg in _SYMMETRIC_ALGS:
        warn.append(
            f"entry {index}: alg '{alg}' is a symmetric MAC family, not publicly verifiable"
        )
    elif alg not in _ASYMMETRIC_ALGS:
        warn.append(
            f"entry {index}: alg '{alg}' is outside the RFC 7518 / EdDSA asymmetric registry"
        )

    has_key_hint = any(
        field in protected_json or field in unprotected for field in _KEY_HINT_FIELDS
    )
    if not has_key_hint:
        warn.append(f"entry {index}: no key-resolution hint ({', '.join(_KEY_HINT_FIELDS)})")

    return fail, warn
