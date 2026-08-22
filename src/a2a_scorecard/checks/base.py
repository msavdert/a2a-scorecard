"""Check contract and the shared probe context.

A check is one class in one module with permanent ClassVar metadata.
Stages run in order; a check runs only if every ID in `requires` finished
PASS or WARN, otherwise it is reported BLOCKED without executing.
"""

from __future__ import annotations

import abc
from typing import Any, ClassVar

import httpx

from a2a_scorecard.config import Settings
from a2a_scorecard.models import CheckResult, CheckStatus


class ProbeContext:
    """Mutable blackboard shared by all checks of one scan."""

    def __init__(self, base_url: str, client: httpx.Client, settings: Settings) -> None:
        self.base_url = base_url.rstrip("/")
        self.client = client
        self.settings = settings
        self.card: dict[str, Any] | None = None
        self.card_url: str | None = None
        self.card_raw: str | None = None
        # "v1" (supportedInterfaces card), "v0.x" (url/preferredTransport card),
        # or "unknown" until the card has been parsed.
        self.spec_generation: str = "unknown"
        self.jsonrpc_endpoint: str | None = None
        self.outcomes: dict[str, CheckStatus] = {}


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
