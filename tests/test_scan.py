from a2a_scorecard.config import Settings
from a2a_scorecard.models import CheckResult, CheckStatus, TargetReport
from a2a_scorecard.scan import run_scan

SETTINGS = Settings(allow_http=True)


def by_id(report: TargetReport) -> dict[str, CheckResult]:
    return {r.check_id: r for r in report.results}


def test_compliant_agent_grades_a(fake_agent) -> None:
    report = run_scan(fake_agent("compliant"), SETTINGS)
    results = by_id(report)
    for check_id in ("C001", "C010", "C011", "C012", "C013", "C020", "C021"):
        assert results[check_id].status is CheckStatus.PASS, (
            f"{check_id}: {results[check_id].evidence}"
        )
    # No security declared at all: C030 SKIPs and must not affect the score
    # or grade (ADR-0007 consequence: v0.1 fixtures keep their grades).
    assert results["C030"].status is CheckStatus.SKIP
    # No signatures declared either: C031 SKIPs too (ADR-0009 consequence:
    # total weight rises from 120 to 130 but unsigned fixtures don't move).
    assert results["C031"].status is CheckStatus.SKIP
    # No capabilities.streaming declared either: C022 SKIPs (ADR-0013
    # consequence: total weight rises from 140 to 150 but this fixture's
    # grade is unaffected).
    assert results["C022"].status is CheckStatus.SKIP
    # The fixture is served over plain http: C032 SKIPs, there is no TLS to
    # inspect (ADR-0010 consequence: total weight rises from 130 to 140 but
    # plain-http fixtures don't move).
    assert results["C032"].status is CheckStatus.SKIP
    # JSON-RPC was applicable and probed by C020: C023 SKIPs per the
    # ping-budget rule (ADR-0014 consequence: total weight rises from 150
    # to 160 but this fixture's grade is unaffected).
    assert results["C023"].status is CheckStatus.SKIP
    assert report.spec_generation == "v1"
    assert report.score == 100.0
    assert report.grade == "A"


def test_missing_card_blocks_downstream(fake_agent) -> None:
    report = run_scan(fake_agent("no-card"), SETTINGS)
    results = by_id(report)
    assert results["C010"].status is CheckStatus.FAIL
    for check_id in ("C011", "C012", "C013", "C020", "C021"):
        assert results[check_id].status is CheckStatus.BLOCKED
    assert report.grade == "F"


def test_unparseable_card_fails_parse_check(fake_agent) -> None:
    report = run_scan(fake_agent("bad-json"), SETTINGS)
    results = by_id(report)
    assert results["C010"].status is CheckStatus.PASS
    assert results["C011"].status is CheckStatus.FAIL
    assert results["C020"].status is CheckStatus.BLOCKED


def test_schema_invalid_card_still_pings(fake_agent) -> None:
    report = run_scan(fake_agent("invalid-card"), SETTINGS)
    results = by_id(report)
    assert results["C012"].status is CheckStatus.FAIL
    assert results["C020"].status is CheckStatus.PASS
    assert report.grade == "B"


def test_card_without_protocol_endpoint(fake_agent) -> None:
    report = run_scan(fake_agent("card-only"), SETTINGS)
    results = by_id(report)
    assert results["C012"].status is CheckStatus.PASS
    assert results["C020"].status is CheckStatus.FAIL
    assert results["C021"].status is CheckStatus.BLOCKED
    assert report.grade == "C"


def test_grpc_only_card_skips_jsonrpc_probes(fake_agent) -> None:
    # A card legally declaring only non-JSONRPC bindings must not be punished
    # for the JSON-RPC probes it cannot answer (reviewer finding, ADR-0005).
    report = run_scan(fake_agent("grpc-only"), SETTINGS)
    results = by_id(report)
    assert results["C013"].status is CheckStatus.PASS
    assert results["C020"].status is CheckStatus.SKIP
    assert results["C021"].status is CheckStatus.SKIP
    assert report.grade == "A"


def test_plain_http_warns_reachability(fake_agent) -> None:
    # Same endpoint that PASSes C001 under SETTINGS (allow_http=True) must
    # WARN once plain http is no longer allowed (docs/SCANNING-POLICY.md).
    report = run_scan(fake_agent("compliant"), Settings(allow_http=False))
    results = by_id(report)
    assert results["C001"].status is CheckStatus.WARN


def test_legacy_card_location_warns(fake_agent) -> None:
    report = run_scan(fake_agent("legacy-location"), SETTINGS)
    results = by_id(report)
    assert results["C010"].status is CheckStatus.WARN


def test_v0x_card_skips_schema_check(fake_agent) -> None:
    report = run_scan(fake_agent("v0-card"), SETTINGS)
    results = by_id(report)
    assert report.spec_generation == "v0.x"
    assert results["C012"].status is CheckStatus.SKIP


def test_version_silent_card_detects_v0x_and_skips(fake_agent) -> None:
    # ADR-0016 regression (a): a card with top-level "url" and no version
    # signal at all must still be classified v0.x from "url" alone, and
    # C012 must SKIP rather than fail it against the v1 schema. This is the
    # exact shape the 2026-08-22 census found causing 124/400 false FAILs.
    report = run_scan(fake_agent("version-silent-card"), SETTINGS)
    results = by_id(report)
    assert report.spec_generation == "v0.x"
    assert results["C012"].status is CheckStatus.SKIP
    assert report.grade != "F"


def test_v1_card_detects_v1_and_schema_passes(fake_agent) -> None:
    # ADR-0016 regression (b): a clean v1 card (supportedInterfaces only,
    # no legacy fields) detects v1 and C012 runs and passes.
    report = run_scan(fake_agent("compliant"), SETTINGS)
    results = by_id(report)
    assert report.spec_generation == "v1"
    assert results["C012"].status is CheckStatus.PASS


def test_v1_card_with_legacy_fields_still_fails_schema(fake_agent) -> None:
    # ADR-0016 regression (c): a card carrying BOTH supportedInterfaces and
    # legacy url/protocolVersion must detect v1 (the v1 signal wins) and
    # C012 must still FAIL: the legacy top-level fields violate the v1
    # schema's additionalProperties:false. This guards against the SKIP fix
    # swallowing a genuine defect.
    report = run_scan(fake_agent("v1-card-with-legacy-fields"), SETTINGS)
    results = by_id(report)
    assert report.spec_generation == "v1"
    assert results["C012"].status is CheckStatus.FAIL


def test_no_generation_signal_card_is_undetermined_and_skips(fake_agent) -> None:
    # ADR-0016 regression (d): a card with neither a v1 nor a v0.x signal is
    # genuinely undetermined. C012 must SKIP - a missing version declaration
    # must never convert into a scored schema failure. This fixture also
    # declares no interface at all, which is a separate, genuine C013
    # failure (unrelated to generation detection) that legitimately drags
    # the grade down; the assertion here is only that C012 itself SKIPs
    # rather than piling on a schema FAIL.
    report = run_scan(fake_agent("no-generation-signal-card"), SETTINGS)
    results = by_id(report)
    assert report.spec_generation == "undetermined"
    assert results["C012"].status is CheckStatus.SKIP


def test_card_without_skills_warns_semantics(fake_agent) -> None:
    report = run_scan(fake_agent("no-skills"), SETTINGS)
    results = by_id(report)
    assert results["C013"].status is CheckStatus.WARN


def test_card_without_interface_fails_semantics(fake_agent) -> None:
    report = run_scan(fake_agent("no-interface"), SETTINGS)
    results = by_id(report)
    assert results["C013"].status is CheckStatus.FAIL
    assert results["C020"].status is CheckStatus.BLOCKED


def test_auth_gated_endpoint_warns_ping(fake_agent) -> None:
    report = run_scan(fake_agent("auth-gated"), SETTINGS)
    results = by_id(report)
    assert results["C020"].status is CheckStatus.WARN
    assert results["C021"].status is CheckStatus.SKIP
    # This fixture's card declares capabilities.streaming: true, so a SKIP
    # here can only come from ctx.auth_gated, not from a missing
    # declaration (ADR-0013): the probe must not be attempted behind the gate.
    assert results["C022"].status is CheckStatus.SKIP
    assert "auth-gated" in results["C022"].evidence


def test_unknown_method_wrong_error_code_warns(fake_agent) -> None:
    report = run_scan(fake_agent("wrong-error-code"), SETTINGS)
    results = by_id(report)
    assert results["C020"].status is CheckStatus.PASS
    assert results["C021"].status is CheckStatus.WARN


def test_unknown_method_without_error_fails(fake_agent) -> None:
    report = run_scan(fake_agent("no-error-on-unknown"), SETTINGS)
    results = by_id(report)
    assert results["C020"].status is CheckStatus.PASS
    assert results["C021"].status is CheckStatus.FAIL


def test_malformed_url_fails_reachability_not_error() -> None:
    report = run_scan("http://[bad", Settings(allow_http=True, timeout_s=0.5))
    results = by_id(report)
    assert results["C001"].status is CheckStatus.FAIL
    assert report.grade == "F"


def test_unreachable_target_fails_cleanly() -> None:
    # Localhost discard port: refused immediately, no traffic leaves the machine.
    report = run_scan("http://127.0.0.1:9", Settings(allow_http=True, timeout_s=0.5))
    results = by_id(report)
    assert results["C001"].status is CheckStatus.FAIL
    assert report.grade == "F"


def test_v0x_card_skips_security_check(fake_agent) -> None:
    # ADR-0007: the sanity rules are written against the v1 card shape, so a
    # v0.x-generation card SKIPs regardless of any security declaration.
    report = run_scan(fake_agent("v0-card"), SETTINGS)
    results = by_id(report)
    assert results["C030"].status is CheckStatus.SKIP
    assert results["C031"].status is CheckStatus.SKIP


def test_v0x_card_with_security_still_skips(fake_agent) -> None:
    # Isolates the v1-only SKIP branch from the no-declaration SKIP branch in
    # test_v0x_card_skips_security_check: this card declares a coherent
    # security scheme, so the only reason it can SKIP is the generation check.
    report = run_scan(fake_agent("v0-card-with-security"), SETTINGS)
    results = by_id(report)
    assert results["C030"].status is CheckStatus.SKIP
    assert "not v1" in results["C030"].evidence
    assert results["C031"].status is CheckStatus.SKIP
    assert "not v1" in results["C031"].evidence


def test_coherent_security_schemes_pass(fake_agent) -> None:
    report = run_scan(fake_agent("security-coherent"), SETTINGS)
    results = by_id(report)
    assert results["C030"].status is CheckStatus.PASS, results["C030"].evidence
    assert report.grade == "A"


def test_dangling_security_reference_fails(fake_agent) -> None:
    report = run_scan(fake_agent("security-dangling-ref"), SETTINGS)
    results = by_id(report)
    assert results["C030"].status is CheckStatus.FAIL
    assert "ghost" in results["C030"].evidence


def test_plain_http_auth_url_warns(fake_agent) -> None:
    report = run_scan(fake_agent("security-plain-http"), SETTINGS)
    results = by_id(report)
    assert results["C030"].status is CheckStatus.WARN
    assert "http://" in results["C030"].evidence


def test_malformed_security_scheme_fails(fake_agent) -> None:
    report = run_scan(fake_agent("security-malformed"), SETTINGS)
    results = by_id(report)
    assert results["C030"].status is CheckStatus.FAIL
    assert "apikey" in results["C030"].evidence


def test_security_schemes_not_object_fails(fake_agent) -> None:
    # securitySchemes is a list, not an object: must FAIL with evidence, not
    # crash the check (which scan.py would otherwise report as ERROR).
    report = run_scan(fake_agent("security-schemes-not-object"), SETTINGS)
    results = by_id(report)
    assert results["C030"].status is CheckStatus.FAIL
    assert "securitySchemes is not an object" in results["C030"].evidence


def test_signed_well_formed_passes(fake_agent) -> None:
    report = run_scan(fake_agent("signed-well-formed"), SETTINGS)
    results = by_id(report)
    assert results["C031"].status is CheckStatus.PASS, results["C031"].evidence


def test_signed_alg_none_fails(fake_agent) -> None:
    report = run_scan(fake_agent("signed-alg-none"), SETTINGS)
    results = by_id(report)
    assert results["C031"].status is CheckStatus.FAIL
    assert "alg is 'none'" in results["C031"].evidence


def test_signed_undecodable_protected_fails(fake_agent) -> None:
    report = run_scan(fake_agent("signed-undecodable-protected"), SETTINGS)
    results = by_id(report)
    assert results["C031"].status is CheckStatus.FAIL
    assert "not base64url-decodable" in results["C031"].evidence


def test_signed_symmetric_alg_warns(fake_agent) -> None:
    report = run_scan(fake_agent("signed-symmetric-alg"), SETTINGS)
    results = by_id(report)
    assert results["C031"].status is CheckStatus.WARN
    assert "HS256" in results["C031"].evidence


def test_signed_missing_key_hint_warns(fake_agent) -> None:
    report = run_scan(fake_agent("signed-missing-key-hint"), SETTINGS)
    results = by_id(report)
    assert results["C031"].status is CheckStatus.WARN
    assert "key-resolution hint" in results["C031"].evidence


def test_signed_not_a_list_fails(fake_agent) -> None:
    report = run_scan(fake_agent("signed-not-a-list"), SETTINGS)
    results = by_id(report)
    assert results["C031"].status is CheckStatus.FAIL
    assert "signatures is not a list" in results["C031"].evidence


def test_streaming_happy_path_passes(fake_agent) -> None:
    report = run_scan(fake_agent("streaming"), SETTINGS)
    results = by_id(report)
    assert results["C022"].status is CheckStatus.PASS, results["C022"].evidence


def test_streaming_unary_drift_warns(fake_agent) -> None:
    # Card declares streaming, but SendStreamingMessage gets an ordinary
    # unary 200 JSON reply instead of an SSE stream: functional drift, WARN.
    report = run_scan(fake_agent("streaming-unary"), SETTINGS)
    results = by_id(report)
    assert results["C022"].status is CheckStatus.WARN
    assert "text/event-stream" in results["C022"].evidence


def test_streaming_garbled_first_event_warns(fake_agent) -> None:
    # Valid SSE stream, but the first event's payload is not a recognizable
    # JSON-RPC response object: distinct WARN path from the unary-drift case.
    report = run_scan(fake_agent("streaming-garbled"), SETTINGS)
    results = by_id(report)
    assert results["C022"].status is CheckStatus.WARN
    assert "did not parse as a JSON-RPC response" in results["C022"].evidence


def test_streaming_rejected_fails(fake_agent) -> None:
    # SSE-framed method-not-found error: the card promised streaming and the
    # wire rejects it.
    report = run_scan(fake_agent("streaming-rejected"), SETTINGS)
    results = by_id(report)
    assert results["C022"].status is CheckStatus.FAIL
    assert "-32601" in results["C022"].evidence or "Method not found" in results["C022"].evidence


def test_streaming_timeout_fails(fake_agent) -> None:
    # Valid SSE headers but no data event ever: must FAIL via the timeout
    # path, bounded by a shrunk stream_timeout_s so the test stays fast.
    report = run_scan(
        fake_agent("streaming-stalls"), Settings(allow_http=True, stream_timeout_s=0.5)
    )
    results = by_id(report)
    assert results["C022"].status is CheckStatus.FAIL
    assert "no SSE data event" in results["C022"].evidence


def test_streaming_trickle_deadline_fails(fake_agent) -> None:
    # A keepalive-style target that never sends a data event but writes an
    # SSE comment line every 0.1s (well inside stream_timeout_s) must not be
    # able to hold the connection open indefinitely by resetting httpx's
    # per-read idle timeout on every comment: the probe must enforce its own
    # absolute deadline and FAIL once stream_timeout_s has elapsed.
    report = run_scan(
        fake_agent("streaming-trickle"), Settings(allow_http=True, stream_timeout_s=0.5)
    )
    results = by_id(report)
    assert results["C022"].status is CheckStatus.FAIL
    assert "no SSE data event" in results["C022"].evidence


def test_streaming_multiline_event_passes(fake_agent) -> None:
    # A legitimate SSE data event spread across several `data:` lines (e.g. a
    # pretty-printed JSON body) must be reassembled by joining the lines with
    # "\n", not truncated at the first line.
    report = run_scan(fake_agent("streaming-multiline"), SETTINGS)
    results = by_id(report)
    assert results["C022"].status is CheckStatus.PASS, results["C022"].evidence


def test_streaming_not_declared_skips(fake_agent) -> None:
    # The plain compliant fixture does not declare capabilities.streaming.
    report = run_scan(fake_agent("compliant"), SETTINGS)
    results = by_id(report)
    assert results["C022"].status is CheckStatus.SKIP
    assert "capabilities.streaming" in results["C022"].evidence


def test_streaming_probe_sends_exactly_one_request(fake_agent) -> None:
    # docs/SCANNING-POLICY.md: at most one streaming request per scan.
    url = fake_agent("streaming")
    run_scan(url, SETTINGS)
    assert fake_agent.streaming_request_count(url) == 1


def test_streaming_no_newline_deadline_fails(fake_agent) -> None:
    # A target that drips bytes containing no line terminator at all must
    # not be able to starve the probe's deadline check: the read loop is
    # byte-oriented (iter_raw), not line-buffered, so the absolute deadline
    # is checked on every chunk regardless of whether a line ever completes.
    report = run_scan(
        fake_agent("streaming-no-newline"), Settings(allow_http=True, stream_timeout_s=0.5)
    )
    results = by_id(report)
    assert results["C022"].status is CheckStatus.FAIL
    assert "no SSE data event" in results["C022"].evidence


def test_streaming_oversized_response_fails(fake_agent) -> None:
    # A single response chunk with no line terminator anywhere, larger than
    # the probe's 64 KiB size bound, must FAIL on the size bound rather than
    # buffering without limit while waiting for a line to complete.
    report = run_scan(fake_agent("streaming-oversized"), SETTINGS)
    results = by_id(report)
    assert results["C022"].status is CheckStatus.FAIL
    assert "exceeded size bound" in results["C022"].evidence


def test_legacy_drift_still_runs_streaming_probe(fake_agent) -> None:
    # C020 WARNs via its legacy message/send retry path (spec drift); C022
    # must still run since WARN is a "runnable" outcome, not BLOCKED
    # (docs/adr/0005-check-architecture-and-grading.md), so a card that also
    # declares streaming must still get its SendStreamingMessage probed.
    report = run_scan(fake_agent("legacy-streaming-drift"), SETTINGS)
    results = by_id(report)
    assert results["C020"].status is CheckStatus.WARN
    assert "legacy" in results["C020"].evidence
    assert results["C022"].status not in (CheckStatus.BLOCKED, CheckStatus.SKIP)
    assert results["C022"].status is CheckStatus.PASS, results["C022"].evidence
