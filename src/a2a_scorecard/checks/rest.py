"""Stage 2: the single REST (HTTP+JSON binding) probe (ADR-0014).

At most one benign `POST {interface url}/message:send` per scan, sent only to
targets whose card declares an HTTP+JSON `supportedInterfaces` entry and only
when the JSON-RPC pings were not applicable (C020's outcome is SKIP), so a
scan never sends more than two message pings in total
(docs/SCANNING-POLICY.md).
"""

from __future__ import annotations

from typing import Any

import httpx

from a2a_scorecard.checks.base import Check, ProbeContext
from a2a_scorecard.checks.protocol import _result_looks_valid, _v1_ping_params
from a2a_scorecard.models import CheckResult, CheckStatus

PATH = "/message:send"


def _http_json_endpoint(card: dict[str, Any] | None) -> str | None:
    if not isinstance(card, dict):
        return None
    interfaces = card.get("supportedInterfaces") or []
    for i in interfaces:
        if (
            isinstance(i, dict)
            and str(i.get("url", "")).strip()
            and i.get("protocolBinding") == "HTTP+JSON"
        ):
            return str(i["url"])
    return None


class RestBindingProbe(Check):
    check_id = "C023"
    title = "Declared HTTP+JSON binding answers a message:send"
    stage = 2
    weight = 10
    requires = ("C013",)

    def run(self, ctx: ProbeContext) -> CheckResult:
        endpoint = _http_json_endpoint(ctx.card)
        if endpoint is None:
            return self.result(
                CheckStatus.SKIP,
                evidence="card declares no HTTP+JSON entry in supportedInterfaces",
            )

        c020_outcome = ctx.outcomes.get("C020")
        if c020_outcome is None:
            # Unreachable in practice: scan.py runs stage-2 checks in check_id
            # order (C020 before C023) and always records an outcome, even
            # BLOCKED/ERROR ones. Kept defensive for direct invocation.
            return self.result(
                CheckStatus.SKIP,
                evidence="C020 outcome unavailable; probe order not established, skipping "
                "defensively",
            )
        if c020_outcome is not CheckStatus.SKIP:
            return self.result(
                CheckStatus.SKIP,
                evidence="JSON-RPC probe was applicable and already sent a message ping; "
                "the two-ping-per-scan budget forbids a second binding's ping "
                "(docs/SCANNING-POLICY.md)",
            )

        try:
            return self._probe(ctx, endpoint)
        except Exception as exc:  # noqa: BLE001 - never let a probe crash the scan
            return self.result(
                CheckStatus.FAIL,
                evidence=f"REST probe failed unexpectedly: {exc}",
            )

    def _probe(self, ctx: ProbeContext, endpoint: str) -> CheckResult:
        url = endpoint.rstrip("/") + PATH
        details: dict[str, Any] = {"endpoint": url, "method": "POST"}
        body = _v1_ping_params()

        try:
            resp = ctx.client.post(url, json=body)
        except (httpx.HTTPError, httpx.InvalidURL) as exc:
            return self.result(
                CheckStatus.FAIL,
                evidence=f"request failed: {exc}",
                details=details,
            )

        details["http_status"] = resp.status_code
        if resp.status_code in (401, 403):
            ctx.auth_gated = True
            return self.result(
                CheckStatus.WARN,
                evidence=f"HTTP {resp.status_code}: endpoint requires auth; not probed further",
                details=details,
            )

        if resp.status_code != 200:
            return self.result(
                CheckStatus.FAIL,
                evidence=f"HTTP {resp.status_code} to {PATH}",
                details=details,
            )

        try:
            parsed: Any = resp.json()
        except ValueError:
            return self.result(
                CheckStatus.FAIL,
                evidence="response body is not JSON",
                details=details,
            )

        if not _result_looks_valid(parsed):
            return self.result(
                CheckStatus.WARN,
                evidence="HTTP 200 but body is not a recognizable Message or Task: "
                "reachable but drifted",
                details=details,
            )

        return self.result(
            CheckStatus.PASS,
            evidence=f"POST {PATH} returned a recognizable Message/Task response",
            details=details,
        )
