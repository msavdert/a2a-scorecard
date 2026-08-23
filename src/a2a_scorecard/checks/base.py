"""Check contract and the shared probe context.

A check is one class in one module with permanent ClassVar metadata.
Stages run in order; a check runs only if every ID in `requires` finished
PASS or WARN, otherwise it is reported BLOCKED without executing.
"""

from __future__ import annotations

import abc
from typing import TYPE_CHECKING, Any, ClassVar

import httpx

from a2a_scorecard.config import Settings
from a2a_scorecard.models import CheckResult, CheckStatus

if TYPE_CHECKING:
    from a2a_scorecard.transport import HostPacer


class ProbeContext:
    """Mutable blackboard shared by all checks of one scan."""

    def __init__(
        self,
        base_url: str,
        client: httpx.Client,
        settings: Settings,
        pacer: HostPacer | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.client = client
        self.settings = settings
        # The TLS check (C032) never goes through `client` - it opens a raw
        # socket - so it takes a pacer slot directly to stay under the same
        # per-host pacing as every other request in the scan (ADR-0020).
        # None only for direct unit construction that doesn't exercise C032.
        self.pacer = pacer
        self.card: dict[str, Any] | None = None
        self.card_url: str | None = None
        self.card_raw: str | None = None
        # "v1" (supportedInterfaces card), "v0.x" (url/preferredTransport card),
        # or "undetermined" until the card has been parsed (ADR-0016).
        self.spec_generation: str = "undetermined"
        # True once the card is known to declare at least one interface URL of
        # any binding; jsonrpc_endpoint stays None for e.g. gRPC-only agents.
        self.has_declared_interface: bool = False
        self.jsonrpc_endpoint: str | None = None
        self.outcomes: dict[str, CheckStatus] = {}
        # Set once a probe hits a 401/403: the policy forbids probing behind
        # an auth gate, so later checks must SKIP rather than re-derive this
        # from an earlier check's status text (docs/SCANNING-POLICY.md).
        self.auth_gated: bool = False


class Check(abc.ABC):
    check_id: ClassVar[str]
    title: ClassVar[str]
    stage: ClassVar[int]
    weight: ClassVar[int]
    requires: ClassVar[tuple[str, ...]] = ()

    @abc.abstractmethod
    def run(self, ctx: ProbeContext) -> CheckResult: ...

    @classmethod
    def result(
        cls,
        status: CheckStatus,
        evidence: str = "",
        details: dict[str, Any] | None = None,
    ) -> CheckResult:
        return CheckResult(
            check_id=cls.check_id,
            title=cls.title,
            status=status,
            weight=cls.weight,
            evidence=evidence,
            details=details or {},
        )
