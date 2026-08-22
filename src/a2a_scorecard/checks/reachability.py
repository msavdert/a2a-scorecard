"""Stage 0: can we reach the endpoint at all, and over what transport."""

from __future__ import annotations

import httpx

from a2a_scorecard.checks.base import Check, ProbeContext
from a2a_scorecard.models import CheckResult, CheckStatus


class EndpointReachable(Check):
    check_id = "C001"
    title = "Endpoint reachable over HTTPS"
    stage = 0
    weight = 10

    def run(self, ctx: ProbeContext) -> CheckResult:
        try:
            resp = ctx.client.get(ctx.base_url)
        except (httpx.HTTPError, httpx.InvalidURL) as exc:
            return self.result(CheckStatus.FAIL, evidence=f"connection failed: {exc}")
        details = {"status_code": resp.status_code, "final_url": str(resp.url)}
        if str(resp.url).startswith("https://"):
            return self.result(
                CheckStatus.PASS, evidence=f"HTTP {resp.status_code} over TLS", details=details
            )
        if ctx.settings.allow_http:
            return self.result(
                CheckStatus.PASS,
                evidence=f"HTTP {resp.status_code}; plain http allowed by settings",
                details=details,
            )
        return self.result(
            CheckStatus.WARN,
            evidence="endpoint served over plain http; spec requires HTTPS in production",
            details=details,
        )
