"""C023 (REST/HTTP+JSON binding probe, ADR-0014)."""

import httpx
import pytest

from a2a_scorecard.checks.base import ProbeContext
from a2a_scorecard.checks.rest import RestBindingProbe
from a2a_scorecard.config import Settings
from a2a_scorecard.models import CheckResult, CheckStatus, TargetReport
from a2a_scorecard.scan import run_scan
from a2a_scorecard.transport import (
    RequestBudgetExceeded,
    ScanAborted,
    ScanLimits,
    ScanTransport,
    Throttled,
)

SETTINGS = Settings(allow_http=True)


def by_id(report: TargetReport) -> dict[str, CheckResult]:
    return {r.check_id: r for r in report.results}


def test_rest_only_ok_passes_and_c020_skips(fake_agent) -> None:
    report = run_scan(fake_agent("rest-only-ok"), SETTINGS)
    results = by_id(report)
    assert results["C020"].status is CheckStatus.SKIP
    assert results["C023"].status is CheckStatus.PASS, results["C023"].evidence


def test_rest_only_drift_warns_and_c020_skips(fake_agent) -> None:
    report = run_scan(fake_agent("rest-only-drift"), SETTINGS)
    results = by_id(report)
    assert results["C020"].status is CheckStatus.SKIP
    assert results["C023"].status is CheckStatus.WARN
    assert "not a recognizable" in results["C023"].evidence


def test_rest_only_rejected_fails_and_c020_skips(fake_agent) -> None:
    report = run_scan(fake_agent("rest-only-rejected"), SETTINGS)
    results = by_id(report)
    assert results["C020"].status is CheckStatus.SKIP
    assert results["C023"].status is CheckStatus.FAIL
    assert "500" in results["C023"].evidence


def test_rest_only_auth_gated_warns_and_c020_skips(fake_agent) -> None:
    report = run_scan(fake_agent("rest-only-auth-gated"), SETTINGS)
    results = by_id(report)
    assert results["C020"].status is CheckStatus.SKIP
    assert results["C023"].status is CheckStatus.WARN
    assert "auth" in results["C023"].evidence


def test_no_http_json_interface_skips(fake_agent) -> None:
    # The plain compliant fixture declares only a JSONRPC interface.
    report = run_scan(fake_agent("compliant"), SETTINGS)
    results = by_id(report)
    assert results["C023"].status is CheckStatus.SKIP
    assert "no HTTP+JSON entry" in results["C023"].evidence


def test_jsonrpc_applicable_skips_rest_ping_budget(fake_agent) -> None:
    # Card declares only JSONRPC: C020 runs (not SKIP), so C023 must SKIP
    # under the two-ping-per-scan budget (docs/SCANNING-POLICY.md).
    report = run_scan(fake_agent("compliant"), SETTINGS)
    results = by_id(report)
    assert results["C020"].status is CheckStatus.PASS
    assert results["C023"].status is CheckStatus.SKIP


def test_rest_binding_probe_sends_exactly_one_request(fake_agent) -> None:
    # docs/SCANNING-POLICY.md: at most one REST message:send ping per scan.
    url = fake_agent("rest-only-ok")
    run_scan(url, SETTINGS)
    assert fake_agent.message_send_request_count(url) == 1


def test_rest_probe_never_fires_when_jsonrpc_applicable(fake_agent) -> None:
    # Ping budget (ADR-0014): a JSON-RPC-capable target already spent the
    # message pings in C020, so the REST probe must not add a third -
    # proven by the counter, not just by C023 reporting SKIP.
    url = fake_agent("compliant")
    run_scan(url, SETTINGS)
    assert fake_agent.message_send_request_count(url) == 0


# --- ScanAborted must propagate, never be swallowed as a scored FAIL --------------
#
# Regression coverage for the bug fixed by adding `except ScanAborted: raise`
# ahead of RestBindingProbe.run's blanket `except Exception` (ADR-0020),
# mirroring the same fix in streaming.py (see tests/test_streaming.py).


def _rest_ctx(base_url: str, client: httpx.Client) -> ProbeContext:
    ctx = ProbeContext(base_url, client, SETTINGS)
    ctx.card = {"supportedInterfaces": [{"url": base_url, "protocolBinding": "HTTP+JSON"}]}
    ctx.outcomes["C020"] = CheckStatus.SKIP
    return ctx


def test_rest_probe_propagates_budget_exceeded() -> None:
    """Direct unit test: a real ScanTransport with the request budget
    already exhausted must raise RequestBudgetExceeded out of
    RestBindingProbe.run, not return a FAIL result."""
    transport = ScanTransport(limits=ScanLimits(max_requests=0), sleep=lambda s: None)
    with httpx.Client(transport=transport) as client:
        ctx = _rest_ctx("http://example.invalid", client)
        with pytest.raises(RequestBudgetExceeded):
            RestBindingProbe().run(ctx)


def test_rest_probe_propagates_throttled() -> None:
    """Direct unit test: a 429 the transport does not retry (a non-GET,
    per ADR-0020) must raise Throttled out of RestBindingProbe.run, not
    return a FAIL result. Uses an httpx.MockTransport as the inner
    transport so this needs no real or fake-agent network I/O."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "999999"})

    transport = ScanTransport(inner=httpx.MockTransport(handler), sleep=lambda s: None)
    with httpx.Client(transport=transport) as client:
        ctx = _rest_ctx("http://example.invalid", client)
        with pytest.raises(Throttled):
            RestBindingProbe().run(ctx)


def test_rest_probe_abort_does_not_produce_a_result() -> None:
    """Same regression, phrased as a non-swallowing check: if the bug were
    present, RestBindingProbe.run would return a CheckResult (status FAIL)
    instead of raising."""
    transport = ScanTransport(limits=ScanLimits(max_requests=0), sleep=lambda s: None)
    with httpx.Client(transport=transport) as client:
        ctx = _rest_ctx("http://example.invalid", client)
        try:
            result = RestBindingProbe().run(ctx)
        except ScanAborted:
            pass
        else:
            pytest.fail(f"expected ScanAborted, got a result instead: {result.status}")


def test_run_scan_raises_scan_aborted_when_rest_probe_hits_budget(fake_agent) -> None:
    """Integration-level regression: a full run_scan against a fake-agent
    mode that reaches the REST probe (C023), with a transport that aborts
    exactly on C023's own request, must raise ScanAborted out of run_scan
    rather than returning a graded TargetReport. The 'rest-only-ok'
    fixture mode PASSes C001 and C010 in exactly one request each and
    C020/C021/C022 all SKIP without a request (verified empirically), so
    a 2-request budget lets those two through and aborts on C023's
    message:send POST, the 3rd."""
    url = fake_agent("rest-only-ok")
    transport = ScanTransport(limits=ScanLimits(max_requests=2), sleep=lambda s: None)

    with pytest.raises(RequestBudgetExceeded):
        run_scan(url, SETTINGS, transport=transport)

    journal = fake_agent.journal(url)
    assert len(journal) == 2
