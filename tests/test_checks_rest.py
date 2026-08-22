"""C023 (REST/HTTP+JSON binding probe, ADR-0014)."""

from a2a_scorecard.config import Settings
from a2a_scorecard.models import CheckResult, CheckStatus, TargetReport
from a2a_scorecard.scan import run_scan

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
