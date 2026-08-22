"""Stage 3: security-scheme sanity (C030).

Inspects only the already-fetched Agent Card; sends no network traffic of
its own, so it fits inside SCANNING-POLICY without amendment (ADR-0007).

Field names below come from the vendored v1 schema
(``src/a2a_scorecard/vendor/a2a-v1.0.1.json``, definitions ``Security
Scheme``, ``API Key Security Scheme``, ``HTTP Auth Security Scheme``,
``O Auth2 Security Scheme``, ``Open Id Connect Security Scheme``, ``Mutual
Tls Security Scheme``, ``O Auth Flows`` and its five flow definitions,
``Security Requirement``). That schema is a proto3-derived discriminated
union: nothing is marked ``required`` (ADR-0004), so the per-type "required"
fields below are a judgment call grounded in what each type needs to
describe a usable credential flow, cross-referenced against the OpenAPI 3.2
Security Scheme Object the schema's own description cites as its model.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from a2a_scorecard.checks.base import Check, ProbeContext
from a2a_scorecard.models import CheckResult, CheckStatus

_KNOWN_SCHEME_TYPES = (
    "apiKeySecurityScheme",
    "httpAuthSecurityScheme",
    "mtlsSecurityScheme",
    "oauth2SecurityScheme",
    "openIdConnectSecurityScheme",
)

# Fields without which a given OAuth2 flow cannot be executed by a client.
_OAUTH_FLOW_REQUIRED: dict[str, tuple[str, ...]] = {
    "authorizationCode": ("authorizationUrl", "tokenUrl"),
    "clientCredentials": ("tokenUrl",),
    "deviceCode": ("deviceAuthorizationUrl", "tokenUrl"),
    "implicit": ("authorizationUrl",),
    "password": ("tokenUrl",),
}

# URL-bearing fields per flow, checked for plain-http (WARN, not FAIL).
_OAUTH_FLOW_URL_FIELDS: dict[str, tuple[str, ...]] = {
    "authorizationCode": ("authorizationUrl", "tokenUrl", "refreshUrl"),
    "clientCredentials": ("tokenUrl", "refreshUrl"),
    "deviceCode": ("deviceAuthorizationUrl", "tokenUrl", "refreshUrl"),
    "implicit": ("authorizationUrl", "refreshUrl"),
    "password": ("tokenUrl", "refreshUrl"),
}


def _nonempty(d: dict[str, Any], key: str) -> bool:
    return bool(str(d.get(key, "")).strip())


def _is_plain_http(url: str) -> bool:
    return urlsplit(url).scheme == "http"


class SecuritySchemeSanity(Check):
    """Cross-checks `securitySchemes` against `securityRequirements` and the
    per-type shape the vendored v1 spec implies (ADR-0007)."""

    check_id = "C030"
    title = "Declared security schemes are coherent"
    stage = 3
    weight = 10
    requires = ("C011",)

    def run(self, ctx: ProbeContext) -> CheckResult:
        assert ctx.card is not None
        if ctx.spec_generation != "v1":
            return self.result(
                CheckStatus.SKIP,
                evidence=f"card generation is '{ctx.spec_generation}', not v1; "
                "the sanity rules are written against the v1 card shape",
            )
        card = ctx.card
        raw_schemes: Any = card.get("securitySchemes") or {}
        requirements: list[Any] = card.get("securityRequirements") or []
        if not raw_schemes and not requirements:
            return self.result(CheckStatus.SKIP, evidence="card declares no security information")

        fail_problems: list[str] = []
        warn_problems: list[str] = []

        if not isinstance(raw_schemes, dict):
            fail_problems.append("securitySchemes is not an object")
            early_details: dict[str, Any] = {
                "declared_schemes": [],
                "referenced_schemes": [],
                "unreferenced_schemes": [],
                "problems": fail_problems,
            }
            return self.result(
                CheckStatus.FAIL, evidence="; ".join(fail_problems), details=early_details
            )
        schemes: dict[str, Any] = raw_schemes

        for name, scheme in schemes.items():
            if not isinstance(scheme, dict):
                fail_problems.append(f"scheme '{name}' is not an object")
                continue
            present_types = [t for t in _KNOWN_SCHEME_TYPES if t in scheme]
            if not present_types:
                warn_problems.append(
                    f"scheme '{name}' has no type recognized by the vendored v1 spec"
                )
                continue
            for stype in present_types:
                body = scheme[stype]
                if not isinstance(body, dict):
                    fail_problems.append(f"scheme '{name}' ({stype}) is not an object")
                    continue
                fail_problems.extend(
                    f"scheme '{name}' ({stype}): {p}" for p in _type_problems(stype, body)
                )
                warn_problems.extend(
                    f"scheme '{name}' ({stype}): {p}"
                    for p in _type_plain_http_warnings(stype, body)
                )

        referenced: set[str] = set()
        for req in requirements:
            if not isinstance(req, dict):
                fail_problems.append("securityRequirements entry is not an object")
                continue
            req_schemes = req.get("schemes") or {}
            if not isinstance(req_schemes, dict):
                fail_problems.append("securityRequirements entry 'schemes' is not an object")
                continue
            for scheme_name in req_schemes:
                referenced.add(scheme_name)
                if scheme_name not in schemes:
                    fail_problems.append(
                        f"'{scheme_name}' referenced in securityRequirements but not "
                        "declared in securitySchemes"
                    )

        unreferenced = sorted(set(schemes) - referenced)
        details: dict[str, Any] = {
            "declared_schemes": sorted(schemes),
            "referenced_schemes": sorted(referenced),
            "unreferenced_schemes": unreferenced,
        }
        if fail_problems:
            details["problems"] = fail_problems
            return self.result(CheckStatus.FAIL, evidence="; ".join(fail_problems), details=details)
        if warn_problems:
            details["problems"] = warn_problems
            return self.result(CheckStatus.WARN, evidence="; ".join(warn_problems), details=details)
        return self.result(
            CheckStatus.PASS,
            evidence=f"{len(schemes)} scheme(s) declared, coherent with securityRequirements",
            details=details,
        )


def _type_problems(stype: str, body: dict[str, Any]) -> list[str]:
    if stype == "apiKeySecurityScheme":
        return [f"missing '{f}'" for f in ("name", "location") if not _nonempty(body, f)]
    if stype == "httpAuthSecurityScheme":
        return [] if _nonempty(body, "scheme") else ["missing 'scheme'"]
    if stype == "mtlsSecurityScheme":
        return []
    if stype == "openIdConnectSecurityScheme":
        return [] if _nonempty(body, "openIdConnectUrl") else ["missing 'openIdConnectUrl'"]
    if stype == "oauth2SecurityScheme":
        return _oauth2_problems(body)
    return []


def _oauth2_problems(body: dict[str, Any]) -> list[str]:
    flows = body.get("flows")
    has_metadata_url = _nonempty(body, "oauth2MetadataUrl")
    if not isinstance(flows, dict) or not flows:
        return [] if has_metadata_url else ["missing 'flows' (or 'oauth2MetadataUrl')"]
    problems: list[str] = []
    any_flow = False
    for flow_name, required in _OAUTH_FLOW_REQUIRED.items():
        flow_body = flows.get(flow_name)
        if flow_body is None:
            continue
        any_flow = True
        if not isinstance(flow_body, dict):
            problems.append(f"flow '{flow_name}' is not an object")
            continue
        problems.extend(
            f"flow '{flow_name}' missing '{f}'" for f in required if not _nonempty(flow_body, f)
        )
    if not any_flow and not has_metadata_url:
        problems.append("'flows' declared but empty, and no 'oauth2MetadataUrl'")
    return problems


def _type_plain_http_warnings(stype: str, body: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    if stype == "openIdConnectSecurityScheme":
        url = str(body.get("openIdConnectUrl", "")).strip()
        if url and _is_plain_http(url):
            warnings.append(f"openIdConnectUrl is plain http: {url}")
    elif stype == "oauth2SecurityScheme":
        url = str(body.get("oauth2MetadataUrl", "")).strip()
        if url and _is_plain_http(url):
            warnings.append(f"oauth2MetadataUrl is plain http: {url}")
        flows = body.get("flows")
        if isinstance(flows, dict):
            for flow_name, url_fields in _OAUTH_FLOW_URL_FIELDS.items():
                flow_body = flows.get(flow_name)
                if not isinstance(flow_body, dict):
                    continue
                for field_name in url_fields:
                    fval = str(flow_body.get(field_name, "")).strip()
                    if fval and _is_plain_http(fval):
                        warnings.append(f"flow '{flow_name}'.{field_name} is plain http: {fval}")
    return warnings
