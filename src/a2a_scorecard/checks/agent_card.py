"""Stage 1: Agent Card discovery, parsing, schema and semantic validation."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from a2a_scorecard import schema
from a2a_scorecard.checks.base import Check, ProbeContext
from a2a_scorecard.models import CheckResult, CheckStatus

WELL_KNOWN = "/.well-known/agent-card.json"
# Pre-v0.3.0 location; still common in the wild.
WELL_KNOWN_LEGACY = "/.well-known/agent.json"


def origin_of(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, "", "", ""))


class AgentCardPresent(Check):
    check_id = "C010"
    title = "Agent Card served at well-known URI"
    stage = 1
    weight = 20
    requires = ("C001",)

    def run(self, ctx: ProbeContext) -> CheckResult:
        origin = origin_of(ctx.base_url)
        for path, legacy in ((WELL_KNOWN, False), (WELL_KNOWN_LEGACY, True)):
            url = origin + path
            try:
                resp = ctx.client.get(url)
            except httpx.HTTPError as exc:
                return self.result(CheckStatus.FAIL, evidence=f"fetch failed: {exc}")
            if resp.status_code == 200:
                ctx.card_url = url
                ctx.card_raw = resp.text
                if legacy:
                    return self.result(
                        CheckStatus.WARN,
                        evidence=f"card only at legacy {WELL_KNOWN_LEGACY}; "
                        f"spec v0.3+ uses {WELL_KNOWN}",
                        details={"card_url": url},
                    )
                return self.result(
                    CheckStatus.PASS, evidence=f"200 at {path}", details={"card_url": url}
                )
        return self.result(
            CheckStatus.FAIL,
            evidence=f"no card at {WELL_KNOWN} or {WELL_KNOWN_LEGACY} on {origin}",
        )


class AgentCardParses(Check):
    check_id = "C011"
    title = "Agent Card is valid JSON"
    stage = 1
    weight = 10
    requires = ("C010",)

    def run(self, ctx: ProbeContext) -> CheckResult:
        assert ctx.card_raw is not None
        try:
            card = json.loads(ctx.card_raw)
        except json.JSONDecodeError as exc:
            return self.result(CheckStatus.FAIL, evidence=f"body is not JSON: {exc}")
        if not isinstance(card, dict):
            return self.result(CheckStatus.FAIL, evidence="card JSON is not an object")
        ctx.card = card
        ctx.spec_generation = _detect_generation(card)
        return self.result(
            CheckStatus.PASS,
            evidence=f"parsed; detected card generation: {ctx.spec_generation}",
            details={"spec_generation": ctx.spec_generation},
        )


def _detect_generation(card: dict[str, Any]) -> str:
    if "supportedInterfaces" in card:
        return "v1"
    if "url" in card and ("preferredTransport" in card or "protocolVersion" in card):
        return "v0.x"
    return "unknown"


class AgentCardSchemaValid(Check):
    check_id = "C012"
    title = "Agent Card validates against official v1 schema"
    stage = 1
    weight = 20
    requires = ("C011",)

    def run(self, ctx: ProbeContext) -> CheckResult:
        assert ctx.card is not None
        if ctx.spec_generation == "v0.x":
            return self.result(
                CheckStatus.SKIP,
                evidence="v0.x-generation card; v1 schema not applicable",
            )
        errors = schema.validate_agent_card(ctx.card)
        if errors:
            shown = errors[:10]
            return self.result(
                CheckStatus.FAIL,
                evidence=f"{len(errors)} schema violation(s); first: {shown[0]}",
                details={"errors": shown},
            )
        return self.result(CheckStatus.PASS, evidence="valid against vendored spec v1.0.1 schema")


class AgentCardSemantics(Check):
    """Proto3-derived schemas mark nothing as required, so schema validity is a
    weak bar; this check enforces the fields a usable card cannot do without."""

    check_id = "C013"
    title = "Agent Card declares usable identity and interface"
    stage = 1
    weight = 15
    requires = ("C011",)

    def run(self, ctx: ProbeContext) -> CheckResult:
        assert ctx.card is not None
        card = ctx.card
        problems: list[str] = []
        for fld in ("name", "description", "version"):
            if not str(card.get(fld, "")).strip():
                problems.append(f"missing or empty '{fld}'")
        endpoint = _jsonrpc_endpoint(ctx)
        if endpoint is None:
            problems.append("no usable interface URL (supportedInterfaces / url)")
        else:
            ctx.jsonrpc_endpoint = endpoint
            if not endpoint.startswith("https://") and not ctx.settings.allow_http:
                problems.append(f"interface URL is not HTTPS: {endpoint}")
        if not card.get("skills"):
            problems.append("no skills declared")
        if problems:
            return self.result(
                CheckStatus.WARN if ctx.jsonrpc_endpoint else CheckStatus.FAIL,
                evidence="; ".join(problems),
                details={"problems": problems},
            )
        return self.result(CheckStatus.PASS, evidence="name, version, interface and skills present")


def _jsonrpc_endpoint(ctx: ProbeContext) -> str | None:
    assert ctx.card is not None
    card = ctx.card
    if ctx.spec_generation == "v1":
        interfaces = card.get("supportedInterfaces") or []
        candidates = [
            i for i in interfaces if isinstance(i, dict) and str(i.get("url", "")).strip()
        ]
        for i in candidates:
            if i.get("protocolBinding", "") in ("JSONRPC", ""):
                return str(i["url"])
        return str(candidates[0]["url"]) if candidates else None
    url = str(card.get("url", "")).strip()
    return url or None
