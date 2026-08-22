"""Stage 2: live JSON-RPC protocol probes.

Both probes here are benign by construction (docs/SCANNING-POLICY.md):
one spec-conformant SendMessage ping, and one intentionally unknown method
name to observe error handling. Nothing mutates remote state beyond the
single ping task, and auth is never bypassed: auth-gated endpoints are
reported as such, not probed further.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import httpx

from a2a_scorecard.checks.base import Check, ProbeContext
from a2a_scorecard.models import CheckResult, CheckStatus

PING_TEXT = "a2a-scorecard conformance probe: please reply with any short message."

METHOD_NOT_FOUND = -32601


def _jsonrpc_call(
    ctx: ProbeContext, endpoint: str, method: str, params: dict[str, Any]
) -> tuple[int | None, dict[str, Any] | None, str]:
    """Return (http_status, parsed_body, error_note). Body is None if not JSON."""
    payload = {
        "jsonrpc": "2.0",
        "id": f"a2a-scorecard-{uuid.uuid4().hex[:8]}",
        "method": method,
        "params": params,
    }
    try:
        resp = ctx.client.post(endpoint, json=payload)
    except httpx.HTTPError as exc:
        return None, None, f"request failed: {exc}"
    try:
        body = resp.json()
    except json.JSONDecodeError:
        return resp.status_code, None, "response body is not JSON"
    if not isinstance(body, dict):
        return resp.status_code, None, "response JSON is not an object"
    return resp.status_code, body, ""


def _v1_ping_params() -> dict[str, Any]:
    return {
        "message": {
            "messageId": str(uuid.uuid4()),
            "role": "ROLE_USER",
            "parts": [{"text": PING_TEXT}],
        }
    }


def _v0_ping_params() -> dict[str, Any]:
    return {
        "message": {
            "messageId": str(uuid.uuid4()),
            "role": "user",
            "parts": [{"kind": "text", "text": PING_TEXT}],
        }
    }


def _result_looks_valid(result: Any) -> bool:
    if not isinstance(result, dict):
        return False
    # v1: SendMessageResponse carries "message" or "task"; v0.x returns the
    # Task/Message object directly, discriminated by "kind" or task fields.
    return bool("message" in result or "task" in result or "kind" in result or "status" in result)


class ProtocolPing(Check):
    check_id = "C020"
    title = "Agent answers a spec-conformant SendMessage"
    stage = 2
    weight = 25
    requires = ("C013",)

    def run(self, ctx: ProbeContext) -> CheckResult:
        endpoint = ctx.jsonrpc_endpoint
        if endpoint is None:
            return self.result(CheckStatus.FAIL, evidence="no interface URL to probe")

        if ctx.spec_generation == "v0.x":
            return self._probe(ctx, endpoint, "message/send", _v0_ping_params(), legacy=False)

        first = self._probe(ctx, endpoint, "SendMessage", _v1_ping_params(), legacy=False)
        if first.status is CheckStatus.FAIL and first.details.get("jsonrpc_error") == (
            METHOD_NOT_FOUND
        ):
            legacy = self._probe(ctx, endpoint, "message/send", _v0_ping_params(), legacy=True)
            if legacy.status is CheckStatus.PASS:
                legacy.status = CheckStatus.WARN
                legacy.evidence = (
                    "v1 card but only legacy v0.x method 'message/send' answered; spec drift"
                )
            return legacy
        return first

    def _probe(
        self,
        ctx: ProbeContext,
        endpoint: str,
        method: str,
        params: dict[str, Any],
        legacy: bool,
    ) -> CheckResult:
        status_code, body, note = _jsonrpc_call(ctx, endpoint, method, params)
        details: dict[str, Any] = {"endpoint": endpoint, "method": method}
        if status_code in (401, 403):
            details["auth_required"] = True
            ctx.outcomes[self.check_id + ":auth"] = CheckStatus.WARN
            return self.result(
                CheckStatus.WARN,
                evidence=f"HTTP {status_code}: endpoint requires auth; not probed further",
                details=details,
            )
        if body is None:
            details["http_status"] = status_code
            return self.result(CheckStatus.FAIL, evidence=note or "no response", details=details)
        if "result" in body:
            if _result_looks_valid(body["result"]):
                return self.result(
                    CheckStatus.PASS,
                    evidence=f"{method} returned a Message/Task result",
                    details=details,
                )
            return self.result(
                CheckStatus.FAIL,
                evidence="JSON-RPC result is not a recognizable Message or Task",
                details=details,
            )
        error = body.get("error")
        if isinstance(error, dict):
            details["jsonrpc_error"] = error.get("code")
            return self.result(
                CheckStatus.FAIL,
                evidence=f"JSON-RPC error {error.get('code')}: {error.get('message')}",
                details=details,
            )
        return self.result(
            CheckStatus.FAIL, evidence="response is neither result nor error", details=details
        )


class ErrorHandling(Check):
    check_id = "C021"
    title = "Unknown method rejected with JSON-RPC -32601"
    stage = 2
    weight = 10
    requires = ("C020",)

    def run(self, ctx: ProbeContext) -> CheckResult:
        endpoint = ctx.jsonrpc_endpoint
        assert endpoint is not None
        if ctx.outcomes.get("C020:auth") is CheckStatus.WARN:
            return self.result(CheckStatus.SKIP, evidence="endpoint is auth-gated")
        status_code, body, note = _jsonrpc_call(ctx, endpoint, "scorecard/unknownMethod", {})
        if body is None:
            return self.result(
                CheckStatus.FAIL,
                evidence=note or f"HTTP {status_code} without JSON-RPC error body",
            )
        error = body.get("error")
        if isinstance(error, dict) and error.get("code") == METHOD_NOT_FOUND:
            return self.result(CheckStatus.PASS, evidence="proper -32601 method-not-found")
        if isinstance(error, dict):
            return self.result(
                CheckStatus.WARN,
                evidence=f"error returned but wrong code: {error.get('code')}",
            )
        return self.result(
            CheckStatus.FAIL, evidence="unknown method did not produce a JSON-RPC error"
        )
