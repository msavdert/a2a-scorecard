"""Stage 2: the single streaming probe (docs/SCANNING-POLICY.md, ADR-0013).

At most one JSON-RPC `SendStreamingMessage` request per scan, sent only to
targets whose card declares `capabilities.streaming: true`. The connection
closes after the first SSE data event or `stream_timeout_s`, whichever comes
first; the probe never retries and never opens a second stream.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

import httpx

from a2a_scorecard.checks.base import Check, ProbeContext
from a2a_scorecard.checks.protocol import _v1_ping_params
from a2a_scorecard.models import CheckResult, CheckStatus

METHOD = "SendStreamingMessage"


def _declares_streaming(card: dict[str, Any] | None) -> bool:
    if not isinstance(card, dict):
        return False
    capabilities = card.get("capabilities")
    if not isinstance(capabilities, dict):
        return False
    return capabilities.get("streaming") is True


def _looks_like_jsonrpc_response(body: Any) -> bool:
    if not isinstance(body, dict):
        return False
    return "jsonrpc" in body and ("result" in body or "error" in body)


class StreamingProbe(Check):
    check_id = "C022"
    title = "Declared streaming support answers a SendStreamingMessage"
    stage = 2
    weight = 10
    requires = ("C020",)

    def run(self, ctx: ProbeContext) -> CheckResult:
        if not _declares_streaming(ctx.card):
            return self.result(
                CheckStatus.SKIP,
                evidence="card does not declare capabilities.streaming",
            )
        if ctx.auth_gated:
            return self.result(
                CheckStatus.SKIP,
                evidence="endpoint is auth-gated; not probed further",
            )
        endpoint = ctx.jsonrpc_endpoint
        if endpoint is None:
            # Unreachable via scan.py's requires-cascade (ADR-0005): C022
            # requires C020, and C020 itself SKIPs (non-JSONRPC-only card) or
            # FAILs (no interface at all) whenever ctx.jsonrpc_endpoint would
            # be None, which cascades to a BLOCKED or SKIPPED C022 before
            # this method ever runs. Kept for type narrowing on the Optional
            # attribute and for direct invocation in tests (see
            # tests/test_streaming.py::test_no_endpoint_guard_skips).
            return self.result(
                CheckStatus.SKIP,
                evidence="no JSON-RPC endpoint to probe",
            )

        try:
            return self._probe(ctx, endpoint)
        except Exception as exc:  # noqa: BLE001 - never let a probe crash the scan
            return self.result(
                CheckStatus.FAIL,
                evidence=f"streaming probe failed unexpectedly: {exc}",
            )

    def _probe(self, ctx: ProbeContext, endpoint: str) -> CheckResult:
        payload = {
            "jsonrpc": "2.0",
            "id": f"a2a-scorecard-{uuid.uuid4().hex[:8]}",
            "method": METHOD,
            "params": _v1_ping_params(),
        }
        details: dict[str, Any] = {"endpoint": endpoint, "method": METHOD}
        timeout = ctx.settings.stream_timeout_s

        try:
            with ctx.client.stream(
                "POST",
                endpoint,
                json=payload,
                headers={"Accept": "text/event-stream"},
                timeout=timeout,
            ) as resp:
                status_code = resp.status_code
                details["http_status"] = status_code
                if status_code != 200:
                    return self.result(
                        CheckStatus.FAIL,
                        evidence=f"HTTP {status_code} to SendStreamingMessage",
                        details=details,
                    )

                content_type = resp.headers.get("Content-Type", "")
                is_stream = content_type.split(";")[0].strip().lower() == "text/event-stream"
                details["content_type"] = content_type
                if not is_stream:
                    return self.result(
                        CheckStatus.WARN,
                        evidence=(
                            f"HTTP 200 but Content-Type is '{content_type}', not "
                            "text/event-stream: declared streaming answered with a unary "
                            "reply (functional drift)"
                        ),
                        details=details,
                    )

                # httpx's `timeout` is a per-read idle timeout: it resets on
                # every byte received, so a target that drips SSE comment
                # lines (": keepalive") more often than `timeout` never trips
                # it and would otherwise be held open indefinitely. Enforce
                # an absolute wall-clock deadline instead (SCANNING-POLICY.md:
                # "first data event or Ns, whichever comes first"), checked
                # on every loop iteration in addition to httpx's own
                # ReadTimeout for the no-bytes-at-all case.
                first_event: str | None = None
                event_lines: list[str] = []
                deadline = time.monotonic() + timeout
                try:
                    for line in resp.iter_lines():
                        if time.monotonic() >= deadline:
                            break
                        if line.startswith("data:"):
                            event_lines.append(line[len("data:") :].strip())
                            continue
                        if line == "":
                            # Blank line: SSE event boundary. A multi-line
                            # `data:` event joins its lines with "\n"; a
                            # blank line with nothing buffered is just
                            # inter-event padding.
                            if event_lines:
                                first_event = "\n".join(event_lines)
                                break
                            continue
                        # Other SSE fields (event:, id:, retry:) or comment
                        # lines (":...") are not data; ignore and keep reading.
                except httpx.ReadTimeout:
                    first_event = None
                finally:
                    resp.close()
        except (httpx.HTTPError, httpx.InvalidURL) as exc:
            return self.result(
                CheckStatus.FAIL,
                evidence=f"request failed: {exc}",
                details=details,
            )

        if first_event is None:
            return self.result(
                CheckStatus.FAIL,
                evidence=(
                    f"no SSE data event received within {timeout}s; connection closed or timed out"
                ),
                details=details,
            )

        try:
            parsed: Any = json.loads(first_event)
        except json.JSONDecodeError:
            parsed = None

        if not _looks_like_jsonrpc_response(parsed):
            return self.result(
                CheckStatus.WARN,
                evidence="first SSE event did not parse as a JSON-RPC response object",
                details=details,
            )

        error = parsed.get("error")
        if isinstance(error, dict):
            details["jsonrpc_error"] = error.get("code")
            return self.result(
                CheckStatus.FAIL,
                evidence=f"JSON-RPC error {error.get('code')}: {error.get('message')}",
                details=details,
            )

        return self.result(
            CheckStatus.PASS,
            evidence="SendStreamingMessage returned an SSE stream with a valid first event",
            details=details,
        )
