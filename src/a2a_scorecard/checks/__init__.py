"""Check registry.

Order is (stage, check_id); scan.py relies on it. Adding a check:
one module, one Check subclass, one entry here, tests, and an ADR if the
check changes grading semantics or probe behavior.
"""

from a2a_scorecard.checks.agent_card import (
    AgentCardParses,
    AgentCardPresent,
    AgentCardSchemaValid,
    AgentCardSemantics,
)
from a2a_scorecard.checks.base import Check, ProbeContext
from a2a_scorecard.checks.protocol import ErrorHandling, ProtocolPing
from a2a_scorecard.checks.reachability import EndpointReachable
from a2a_scorecard.checks.security import SecuritySchemeSanity
from a2a_scorecard.checks.signature import AgentCardSignatureStructure
from a2a_scorecard.checks.tls import TlsPosture

ALL_CHECKS: list[type[Check]] = [
    EndpointReachable,
    AgentCardPresent,
    AgentCardParses,
    AgentCardSchemaValid,
    AgentCardSemantics,
    ProtocolPing,
    ErrorHandling,
    SecuritySchemeSanity,
    AgentCardSignatureStructure,
    TlsPosture,
]

__all__ = ["ALL_CHECKS", "Check", "ProbeContext"]
