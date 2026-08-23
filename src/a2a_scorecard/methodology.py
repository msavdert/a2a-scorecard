"""Grading methodology manifest and its digest (ADR-0021).

`manifest_digest()` is stamped on every dataset record so a historical row
stays interpretable without access to the source tree that produced it: it
answers "did the ruler change" at row level. Change management for this
module itself is spelled out in ADR-0021's "CI guards" section - a golden
file per GRADING_VERSION under docs/methodology/, and a check-ID uniqueness
guard for CLAUDE.md rule 3.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from a2a_scorecard.checks import ALL_CHECKS, Check

_CHECK_ID_RE = re.compile(r"^C\d{3}$")


def manifest(checks: list[type[Check]] | None = None) -> list[dict[str, Any]]:
    """`[{check_id, weight}]` sorted by check_id, derived from ALL_CHECKS.

    Title and stage are deliberately excluded: they are cosmetic, and a
    typo fix in a title must not read as a methodology change (ADR-0021).
    """
    source = ALL_CHECKS if checks is None else checks
    return sorted(
        ({"check_id": c.check_id, "weight": c.weight} for c in source),
        key=lambda entry: entry["check_id"],
    )


def manifest_digest(checks: list[type[Check]] | None = None) -> str:
    """sha256 over canonical JSON of manifest(), prefixed "sha256:".

    Canonical form is pinned explicitly (sorted keys, compact separators,
    UTF-8) rather than left to json.dumps defaults, so the digest is
    reproducible across Python versions.
    """
    canonical = json.dumps(
        manifest(checks),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def check_id_uniqueness_errors(checks: list[type[Check]] | None = None) -> list[str]:
    """Problems with check_id assignment across ALL_CHECKS; empty when clean.

    CLAUDE.md rule 3: check IDs are permanent, never renumbered or reused.
    Nothing enforced that before this guard existed.
    """
    source = ALL_CHECKS if checks is None else checks
    errors: list[str] = []

    seen: dict[str, list[type[Check]]] = {}
    for c in source:
        seen.setdefault(c.check_id, []).append(c)
    for check_id, owners in sorted(seen.items()):
        if len(owners) > 1:
            names = ", ".join(o.__name__ for o in owners)
            errors.append(f"duplicate check_id {check_id!r} used by: {names}")

    for c in source:
        if not _CHECK_ID_RE.match(c.check_id):
            errors.append(
                f"malformed check_id {c.check_id!r} on {c.__name__}: "
                f"expected shape C followed by exactly three digits"
            )

    return errors
