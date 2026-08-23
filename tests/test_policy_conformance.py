"""Each test here names the docs/SCANNING-POLICY.md line it enforces, and
enforces it as a regression test rather than a review item (ADR-0020).

Tests never touch the network: every target is the in-process fake agent
(CLAUDE.md rule 2).
"""

from __future__ import annotations

import contextlib
import re

import httpx
import pytest

from a2a_scorecard import USER_AGENT
from a2a_scorecard.batch import BatchConfig, BatchOutcome, BatchRecord, run_batch
from a2a_scorecard.checks.agent_card import AgentCardPresent
from a2a_scorecard.checks.base import ProbeContext
from a2a_scorecard.checks.protocol import ErrorHandling, ProtocolPing
from a2a_scorecard.checks.reachability import EndpointReachable
from a2a_scorecard.checks.rest import RestBindingProbe
from a2a_scorecard.checks.streaming import StreamingProbe
from a2a_scorecard.config import Settings
from a2a_scorecard.models import CheckStatus
from a2a_scorecard.scan import run_scan
from a2a_scorecard.targets import Exclusion, Source, Target
from a2a_scorecard.transport import (
    RequestBudgetExceeded,
    ScanAborted,
    ScanLimits,
    ScanTransport,
)

SETTINGS = Settings(allow_http=True)

# Every mode FakeAgentHandler supports, except:
# - "redirect-loop": deliberately unbounded, its own dedicated test below.
# - "barrier"/"cross-host-interface": safe here (they no-op back to normal
#   behavior without a barrier/second_server_url attached), included.
ALL_MODES = [
    "compliant",
    "no-card",
    "bad-json",
    "invalid-card",
    "card-only",
    "grpc-only",
    "legacy-location",
    "v0-card",
    "version-silent-card",
    "v1-card-with-legacy-fields",
    "no-generation-signal-card",
    "no-skills",
    "no-interface",
    "auth-gated",
    "wrong-error-code",
    "no-error-on-unknown",
    "security-coherent",
    "security-dangling-ref",
    "security-plain-http",
    "security-malformed",
    "security-schemes-not-object",
    "v0-card-with-security",
    "signed-well-formed",
    "signed-alg-none",
    "signed-undecodable-protected",
    "signed-symmetric-alg",
    "signed-missing-key-hint",
    "signed-not-a-list",
    "streaming",
    "streaming-unary",
    "streaming-rejected",
    "streaming-stalls",
    "streaming-garbled",
    "streaming-trickle",
    "streaming-multiline",
    "streaming-no-newline",
    "streaming-oversized",
    "legacy-streaming-drift",
    "rest-only-ok",
    "rest-only-drift",
    "rest-only-rejected",
    "rest-only-auth-gated",
    "throttle-once",
    "throttle-always",
    "throttle-post",
    "throttle-http-date",
    "throttle-garbage",
    "throttle-huge",
    "barrier",
    "cross-host-interface",
    "slow",
]

# docs/SCANNING-POLICY.md: "Every request carries the User-Agent
# a2a-scorecard/<version> (conformance scanner; <repo URL>) with a working
# contact path (GitHub issues)."
_USER_AGENT_RE = re.compile(r"^a2a-scorecard/\S+ \(conformance scanner; https://\S+\)$")


def _run_and_swallow_aborts(url: str) -> None:
    """Run a scan, tolerating the abort types this policy suite expects
    some modes to legitimately hit (throttling, budget, deadline) - the
    point of these tests is what was *sent* before/around the abort, not
    whether the scan finished."""
    with contextlib.suppress(ScanAborted):
        run_scan(url, SETTINGS, transport=ScanTransport(sleep=lambda s: None))


# --- "A single scan sends fewer than 10 requests to a target" ---------------------


def test_scan_never_exceeds_nine_requests_per_target(fake_agent) -> None:
    for mode in ALL_MODES:
        url = fake_agent(mode)
        _run_and_swallow_aborts(url)
        journal = fake_agent.journal(url)
        assert len(journal) <= 9, f"mode={mode!r} issued {len(journal)} requests: {journal}"


def test_redirect_loop_hits_budget_exceeded_at_exactly_nine_requests(fake_agent) -> None:
    """`max_redirects` is scan.py's concern (ADR-0020: set to 3 there so a
    real scan never gets close to the budget on redirects alone); this
    transport-level test uses a generous redirect allowance so it is the
    9-request budget, not max_redirects, being exercised."""
    url = fake_agent("redirect-loop")
    transport = ScanTransport(sleep=lambda s: None)
    with (
        httpx.Client(transport=transport, follow_redirects=True, max_redirects=20) as client,
        pytest.raises(RequestBudgetExceeded),
    ):
        client.get(url)

    journal = fake_agent.journal(url)
    assert len(journal) == 9


# --- "at most three message-bearing requests per scan" (ADR-0023) ----------------


def test_at_most_one_streaming_or_rest_ping_per_scan(fake_agent) -> None:
    """The streaming probe (C022) and the REST message:send probe (C023)
    are mutually exclusive by construction (C023 only fires when C020's
    JSON-RPC probe was SKIP, and streaming requires a JSON-RPC endpoint at
    all) - so across every mode, including every throttle mode, their
    counts never both fire and never exceed 1 combined."""
    for mode in ALL_MODES:
        url = fake_agent(mode)
        _run_and_swallow_aborts(url)
        total = fake_agent.streaming_request_count(url) + fake_agent.message_send_request_count(url)
        assert total <= 1, f"mode={mode!r}: {total} streaming+REST pings"


def test_jsonrpc_ping_never_exceeds_v1_plus_legacy_retry(fake_agent) -> None:
    """Policy: one v1 SendMessage, plus a single legacy message/send retry
    sent only when the v1 method is rejected with method-not-found - at
    most 2 raw JSON-RPC ping requests per scan, across every mode."""
    for mode in ALL_MODES:
        url = fake_agent(mode)
        _run_and_swallow_aborts(url)
        count = fake_agent.jsonrpc_ping_count(url)
        assert count <= 2, f"mode={mode!r} sent {count} JSON-RPC SendMessage-family requests"


def test_message_bearing_requests_never_exceed_three(fake_agent) -> None:
    """Policy (ADR-0023): at most two JSON-RPC pings, or one REST ping
    instead, plus at most one streaming request - three message-bearing
    requests in total, across every mode.

    This is the assertion that found the discrepancy ADR-0023 records: the
    policy previously said "two in total", while a v1 card declaring
    streaming whose endpoint rejects the v1 method legitimately sends
    three. The prose was wrong, not the scanner - but nothing was checking
    the prose, so keep this test pinned to the number the policy states.
    """
    for mode in ALL_MODES:
        url = fake_agent(mode)
        _run_and_swallow_aborts(url)
        jsonrpc = fake_agent.jsonrpc_ping_count(url)
        streaming_or_rest = fake_agent.streaming_request_count(
            url
        ) + fake_agent.message_send_request_count(url)
        total = jsonrpc + streaming_or_rest
        assert total <= 3, (
            f"mode={mode!r}: {total} message-bearing requests "
            f"({jsonrpc} JSON-RPC + {streaming_or_rest} streaming/REST)"
        )


# --- "Every request carries the User-Agent [...]" ---------------------------------


def test_user_agent_present_and_policy_shaped_on_every_request(fake_agent) -> None:
    for mode in ALL_MODES:
        url = fake_agent(mode)
        _run_and_swallow_aborts(url)
        for _start, _end, _method, path, user_agent in fake_agent.journal(url):
            assert user_agent, f"mode={mode!r} path={path!r}: no User-Agent header"
            assert _USER_AGENT_RE.match(user_agent), (
                f"mode={mode!r} path={path!r}: User-Agent {user_agent!r} is not policy-shaped"
            )


def test_user_agent_matches_the_configured_scanner_identity(fake_agent) -> None:
    url = fake_agent("compliant")
    _run_and_swallow_aborts(url)
    journal = fake_agent.journal(url)
    assert journal
    assert all(user_agent == USER_AGENT for *_rest, user_agent in journal)


# --- "Batch scanning serializes requests per host" (excluded target) --------------


def test_excluded_target_is_never_contacted() -> None:
    source = Source(directory="test", ref="test", kind="registry", observed_at="2026-01-01")
    target = Target(
        target="http://excluded.example.invalid",
        operator="excluded-operator",
        sources=[source],
        first_seen="2026-01-01",
    )
    exclusion = Exclusion(pattern="excluded.example.invalid", scope="host")
    records: list[BatchRecord] = []
    config = BatchConfig(exclusions=[exclusion])

    run_batch([target], records.append, config, sleep=lambda s: None)

    assert len(records) == 1
    assert records[0].outcome is BatchOutcome.EXCLUDED


# --- Every check must let ScanAborted propagate, never score it -------------------
#
# Regression coverage for the class of bug ADR-0020 warns about by name:
# "scan.py's blanket except Exception... must re-raise ScanAborted first, or
# every abort becomes a scored ERROR" - and the same trap for any check that
# wraps its own probe in a catch-all (streaming.py and rest.py both did,
# fixed by adding `except ScanAborted: raise` ahead of their `except
# Exception`; see tests/test_streaming.py and tests/test_checks_rest.py for
# the check-specific regression tests). This test drives every check that
# actually issues a request through `ctx.client` generically, with the
# request budget pre-exhausted, and asserts none of them convert the abort
# into a scored result.
#
# Coverage note - not every check is here:
# - EndpointReachable (C001), AgentCardPresent (C010), ProtocolPing (C020),
#   ErrorHandling (C021), StreamingProbe (C022) and RestBindingProbe (C023)
#   are covered here: each calls `ctx.client` directly and can be driven
#   generically by pre-building a ProbeContext that satisfies its
#   preconditions and handing it an aborting client.
# - TlsPosture (C032) is NOT covered here: it never goes through
#   `ctx.client` at all (a raw socket, paced via `ctx.pacer.slot` directly -
#   see checks/tls.py and ADR-0020), so an aborting *client* transport
#   cannot reach it. It has no `except Exception` around its handshake call
#   in the first place, so it was never vulnerable to this bug; its own
#   regression (a different bug - the pacer key crash) is covered in
#   tests/test_tls.py and tests/test_transport.py.
# - AgentCardParses, AgentCardSchemaValid, AgentCardSemantics,
#   SecuritySchemeSanity and AgentCardSignatureStructure are NOT covered
#   here: none of them call `ctx.client` - they operate on `ctx.card` /
#   `ctx.card_raw`, already populated by an earlier check - so there is no
#   request for a transport-level abort to interrupt.
#
# For future check authors: the pattern to watch for is a check that wraps
# its own probe in `except Exception` (to keep a crashing probe from
# killing the scan) without an `except ScanAborted: raise` ahead of it -
# ScanAborted deliberately does not derive from httpx.HTTPError (see
# transport.py), so a narrower `except (httpx.HTTPError, httpx.InvalidURL)`
# alone does not catch it and is safe; a blanket `except Exception` does
# catch it and is not, unless ScanAborted is re-raised first.


def _aborting_client() -> httpx.Client:
    transport = ScanTransport(limits=ScanLimits(max_requests=0), sleep=lambda s: None)
    return httpx.Client(transport=transport)


def _ctx_reachable(base_url: str, client: httpx.Client) -> ProbeContext:
    return ProbeContext(base_url, client, SETTINGS)


def _ctx_card_present(base_url: str, client: httpx.Client) -> ProbeContext:
    return ProbeContext(base_url, client, SETTINGS)


def _ctx_protocol_ping(base_url: str, client: httpx.Client) -> ProbeContext:
    ctx = ProbeContext(base_url, client, SETTINGS)
    ctx.jsonrpc_endpoint = base_url
    return ctx


def _ctx_error_handling(base_url: str, client: httpx.Client) -> ProbeContext:
    ctx = ProbeContext(base_url, client, SETTINGS)
    ctx.jsonrpc_endpoint = base_url
    return ctx


def _ctx_streaming(base_url: str, client: httpx.Client) -> ProbeContext:
    ctx = ProbeContext(base_url, client, SETTINGS)
    ctx.card = {"capabilities": {"streaming": True}}
    ctx.jsonrpc_endpoint = base_url
    return ctx


def _ctx_rest(base_url: str, client: httpx.Client) -> ProbeContext:
    ctx = ProbeContext(base_url, client, SETTINGS)
    ctx.card = {"supportedInterfaces": [{"url": base_url, "protocolBinding": "HTTP+JSON"}]}
    ctx.outcomes["C020"] = CheckStatus.SKIP
    return ctx


_GENERIC_ABORT_CASES = [
    (EndpointReachable, _ctx_reachable),
    (AgentCardPresent, _ctx_card_present),
    (ProtocolPing, _ctx_protocol_ping),
    (ErrorHandling, _ctx_error_handling),
    (StreamingProbe, _ctx_streaming),
    (RestBindingProbe, _ctx_rest),
]


@pytest.mark.parametrize(
    "check_cls,ctx_builder",
    _GENERIC_ABORT_CASES,
    ids=[check_cls.check_id for check_cls, _ in _GENERIC_ABORT_CASES],
)
def test_check_propagates_scan_aborted_generically(check_cls, ctx_builder) -> None:
    with _aborting_client() as client:
        ctx = ctx_builder("http://example.invalid", client)
        with pytest.raises(ScanAborted):
            check_cls().run(ctx)
