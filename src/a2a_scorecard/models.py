"""Result types shared by the whole scanner.

Check IDs, statuses and the report shape are public API once published:
never rename or reuse them. See docs/adr/0005-check-architecture-and-grading.md.
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass, field
from typing import Any

# Evidence is a free-text field that can echo bytes read off the network
# (probe error messages, response snippets); it ends up printed raw to a
# terminal by cli.py. Strip C0/C1 control characters and ESC (which drives
# ANSI escape sequences) other than the two whitespace characters we want to
# keep, and cap the length so a misbehaving or hostile target can't grow it
# without bound.
_EVIDENCE_MAX_LEN = 500
_CONTROL_CHARS_RE = re.compile("[\x00-\x08\x0b-\x1f\x7f-\x9f]")


def _sanitize_evidence(evidence: str) -> str:
    cleaned = _CONTROL_CHARS_RE.sub(" ", evidence)
    if len(cleaned) > _EVIDENCE_MAX_LEN:
        cleaned = cleaned[:_EVIDENCE_MAX_LEN] + "..."
    return cleaned


class CheckStatus(enum.Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    # Dependency failed, check could not run. Counts against the score.
    BLOCKED = "blocked"
    # Not applicable to this target (e.g. v1 schema check on a v0.x card).
    # Excluded from the score entirely.
    SKIP = "skip"
    # The check itself crashed. Counts against the score like FAIL.
    ERROR = "error"


@dataclass
class CheckResult:
    check_id: str
    title: str
    status: CheckStatus
    weight: int
    evidence: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.evidence = _sanitize_evidence(self.evidence)

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "title": self.title,
            "status": self.status.value,
            "weight": self.weight,
            "evidence": self.evidence,
            "details": self.details,
        }


@dataclass
class TargetReport:
    target: str
    scanned_at: str
    scanner_version: str
    grading_version: str
    spec_generation: str
    results: list[CheckResult]
    score: float
    grade: str
    # Probe coverage (ADR-0015): the weight the score was computed over
    # versus the total registered weight. Informational; never alters
    # score or grade.
    applicable_weight: int
    max_weight: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "scanned_at": self.scanned_at,
            "scanner_version": self.scanner_version,
            "grading_version": self.grading_version,
            "spec_generation": self.spec_generation,
            "score": self.score,
            "grade": self.grade,
            "applicable_weight": self.applicable_weight,
            "max_weight": self.max_weight,
            "results": [r.to_dict() for r in self.results],
        }
