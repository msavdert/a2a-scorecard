"""Result types shared by the whole scanner.

Check IDs, statuses and the report shape are public API once published:
never rename or reuse them. See docs/adr/0005-check-architecture-and-grading.md.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


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
    spec_generation: str
    results: list[CheckResult]
    score: float
    grade: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "scanned_at": self.scanned_at,
            "scanner_version": self.scanner_version,
            "spec_generation": self.spec_generation,
            "score": self.score,
            "grade": self.grade,
            "results": [r.to_dict() for r in self.results],
        }
