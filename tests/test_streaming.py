"""Unit test for C022's defensive no-endpoint guard, which is unreachable
through a normal scan (see the comment on StreamingProbe.run): C022 requires
C020 (docs/adr/0005), and C020 itself SKIPs or FAILs in every case that would
otherwise leave ctx.jsonrpc_endpoint None, which cascades to a BLOCKED or
SKIPPED C022 before this branch runs. Exercised directly against a hand-built
ProbeContext, following the tests/test_signature.py pattern, so coverage does
not silently go stale."""

from __future__ import annotations

import httpx

from a2a_scorecard.checks.base import ProbeContext
from a2a_scorecard.checks.streaming import StreamingProbe
from a2a_scorecard.config import Settings
from a2a_scorecard.models import CheckStatus


def test_no_endpoint_guard_skips() -> None:
    ctx = ProbeContext("http://example.invalid", httpx.Client(), Settings(allow_http=True))
    ctx.card = {"capabilities": {"streaming": True}}
    ctx.jsonrpc_endpoint = None
    result = StreamingProbe().run(ctx)
    assert result.status is CheckStatus.SKIP
    assert "no JSON-RPC endpoint to probe" in result.evidence
