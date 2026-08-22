"""Scanner settings.

Defaults implement docs/SCANNING-POLICY.md; loosening them for a real
target is a policy change, not a code preference.
"""

from __future__ import annotations

from dataclasses import dataclass

from a2a_scorecard import USER_AGENT


@dataclass
class Settings:
    timeout_s: float = 10.0
    # Bound for the single streaming probe (C022): the connection closes
    # after the first SSE data event or this many seconds, whichever comes
    # first, per docs/SCANNING-POLICY.md's streaming request rule.
    stream_timeout_s: float = 10.0
    user_agent: str = USER_AGENT
    # Only for local development and tests against in-process fixtures.
    # Real scans of http:// endpoints must keep this False so the
    # transport-security check can degrade them honestly.
    allow_http: bool = False
