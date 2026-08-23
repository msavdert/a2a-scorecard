"""Unit test for C022's defensive no-endpoint guard, which is unreachable
through a normal scan (see the comment on StreamingProbe.run): C022 requires
C020 (docs/adr/0005), and C020 itself SKIPs or FAILs in every case that would
otherwise leave ctx.jsonrpc_endpoint None, which cascades to a BLOCKED or
SKIPPED C022 before this branch runs. Exercised directly against a hand-built
ProbeContext, following the tests/test_signature.py pattern, so coverage does
not silently go stale."""

from __future__ import annotations

import httpx
import pytest

from a2a_scorecard.checks.base import ProbeContext
from a2a_scorecard.checks.streaming import StreamingProbe
from a2a_scorecard.config import Settings
from a2a_scorecard.models import CheckStatus
from a2a_scorecard.scan import run_scan
from a2a_scorecard.transport import (
    RequestBudgetExceeded,
    ScanAborted,
    ScanLimits,
    ScanTransport,
    Throttled,
)

SETTINGS = Settings(allow_http=True)


def test_no_endpoint_guard_skips() -> None:
    ctx = ProbeContext("http://example.invalid", httpx.Client(), Settings(allow_http=True))
    ctx.card = {"capabilities": {"streaming": True}}
    ctx.jsonrpc_endpoint = None
    result = StreamingProbe().run(ctx)
    assert result.status is CheckStatus.SKIP
    assert "no JSON-RPC endpoint to probe" in result.evidence


# --- ScanAborted must propagate, never be swallowed as a scored FAIL --------------
#
# Regression coverage for the bug fixed by adding `except ScanAborted: raise`
# ahead of StreamingProbe.run's blanket `except Exception` (ADR-0020). Before
# that fix, ScanAborted (which deliberately does NOT derive from
# httpx.HTTPError, see transport.py) slipped past the narrow
# `except (httpx.HTTPError, httpx.InvalidURL)` in `_probe` and was caught by
# the outer `except Exception`, turning a budget/throttle abort into a scored
# FAIL instead of aborting the whole scan.


def _streaming_ctx(base_url: str, client: httpx.Client) -> ProbeContext:
    ctx = ProbeContext(base_url, client, SETTINGS)
    ctx.card = {"capabilities": {"streaming": True}}
    ctx.jsonrpc_endpoint = base_url
    return ctx


def test_streaming_probe_propagates_budget_exceeded() -> None:
    """Direct unit test: a real ScanTransport with the request budget
    already exhausted must raise RequestBudgetExceeded out of
    StreamingProbe.run, not return a FAIL result."""
    transport = ScanTransport(limits=ScanLimits(max_requests=0), sleep=lambda s: None)
    with httpx.Client(transport=transport) as client:
        ctx = _streaming_ctx("http://example.invalid", client)
        with pytest.raises(RequestBudgetExceeded):
            StreamingProbe().run(ctx)


def test_streaming_probe_propagates_throttled() -> None:
    """Direct unit test: a 429 that the transport decides not to retry (a
    non-GET, per ADR-0020) must raise Throttled out of StreamingProbe.run,
    not return a FAIL result. Uses an httpx.MockTransport as the inner
    transport so this is deterministic and needs no real or fake-agent
    network I/O."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "999999"})

    transport = ScanTransport(inner=httpx.MockTransport(handler), sleep=lambda s: None)
    with httpx.Client(transport=transport) as client:
        ctx = _streaming_ctx("http://example.invalid", client)
        with pytest.raises(Throttled):
            StreamingProbe().run(ctx)


def test_streaming_probe_abort_does_not_produce_a_result(fake_agent) -> None:
    """Same regression, phrased as a non-swallowing check: if the bug were
    present, StreamingProbe.run would return a CheckResult (status FAIL)
    instead of raising."""
    transport = ScanTransport(limits=ScanLimits(max_requests=0), sleep=lambda s: None)
    with httpx.Client(transport=transport) as client:
        ctx = _streaming_ctx("http://example.invalid", client)
        try:
            result = StreamingProbe().run(ctx)
        except ScanAborted:
            pass
        else:
            pytest.fail(f"expected ScanAborted, got a result instead: {result.status}")


def test_run_scan_raises_scan_aborted_when_streaming_probe_hits_budget(fake_agent) -> None:
    """Integration-level regression: a full run_scan against a fake-agent
    mode that reaches the streaming probe (C022), with a transport that
    aborts exactly on C022's own request, must raise ScanAborted out of
    run_scan rather than returning a graded TargetReport. The 'streaming'
    fixture mode PASSes C001, C010, C020 and C021 in exactly one request
    each (verified empirically), so a 4-request budget lets those four
    through and aborts on C022's SendStreamingMessage POST, the 5th."""
    url = fake_agent("streaming")
    transport = ScanTransport(limits=ScanLimits(max_requests=4), sleep=lambda s: None)

    with pytest.raises(RequestBudgetExceeded):
        run_scan(url, SETTINGS, transport=transport)

    journal = fake_agent.journal(url)
    assert len(journal) == 4
