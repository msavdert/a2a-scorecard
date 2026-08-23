"""Guards for ADR-0021's methodology manifest.

Read narrowly: this file only exercises methodology.py and the additive
SPEC_VERSION constant in schema.py. It does not touch dataset.py, which is
implemented separately.
"""

from __future__ import annotations

import json
import re
from importlib import resources
from pathlib import Path

from a2a_scorecard import methodology, schema
from a2a_scorecard.checks import ALL_CHECKS, Check
from a2a_scorecard.grading import GRADING_VERSION

_REPO_ROOT = Path(__file__).resolve().parent.parent
_GOLDEN_PATH = _REPO_ROOT / "docs" / "methodology" / f"grading-{GRADING_VERSION}.json"


class _FakeCheck(Check):
    def run(self, ctx):  # type: ignore[no-untyped-def]
        raise NotImplementedError


def _make_check(check_id: str, weight: int = 10) -> type[Check]:
    return type(
        f"Fake_{check_id}",
        (_FakeCheck,),
        {"check_id": check_id, "title": "fake", "stage": 0, "weight": weight},
    )


# --- digest guard against the committed golden -----------------------------


def test_manifest_digest_matches_committed_golden() -> None:
    golden = json.loads(_GOLDEN_PATH.read_text())
    computed = methodology.manifest_digest()
    assert computed == golden["digest"], (
        f"manifest_digest() = {computed!r} but {_GOLDEN_PATH} records "
        f"{golden['digest']!r} for grading_version {GRADING_VERSION!r}.\n\n"
        "The set of checks or a check's weight changed since this golden was "
        "generated. Per ADR-0021 there are exactly two legal remedies:\n"
        "  1. If no dataset has been published yet, this change is a normal "
        "methodology edit: regenerate the golden file "
        f"({_GOLDEN_PATH.relative_to(_REPO_ROOT)}) from "
        "methodology.manifest()/manifest_digest() and commit it alongside "
        "this change.\n"
        "  2. If a dataset has already been published, GRADING_VERSION in "
        "grading.py must never move backward under readers relying on it: "
        "bump GRADING_VERSION and add a new "
        "docs/methodology/grading-<new version>.json golden instead of "
        "editing this one.\n"
        "Do not edit this golden file by hand in either case - generate it "
        "from code so the digest it records is provably what the code "
        "produces."
    )
    assert golden["grading_version"] == GRADING_VERSION
    assert golden["manifest"] == methodology.manifest()


def test_golden_file_has_trailing_newline() -> None:
    assert _GOLDEN_PATH.read_bytes().endswith(b"\n")


# --- check-ID uniqueness guard ----------------------------------------------


def test_all_checks_has_no_id_violations() -> None:
    errors = methodology.check_id_uniqueness_errors()
    assert errors == [], (
        "CLAUDE.md rule 3: check IDs are permanent, never renumbered or "
        f"reused. Violations found in ALL_CHECKS: {errors}"
    )


def test_check_id_uniqueness_errors_detects_duplicate() -> None:
    a = _make_check("C001")
    b = _make_check("C001")
    c = _make_check("C002")
    errors = methodology.check_id_uniqueness_errors([a, b, c])
    assert len(errors) == 1
    assert "duplicate check_id 'C001'" in errors[0]


def test_check_id_uniqueness_errors_detects_malformed_id() -> None:
    bad = _make_check("C1")
    good = _make_check("C002")
    errors = methodology.check_id_uniqueness_errors([bad, good])
    assert len(errors) == 1
    assert "malformed check_id 'C1'" in errors[0]


def test_check_id_uniqueness_errors_clean_input_is_empty() -> None:
    a = _make_check("C001")
    b = _make_check("C002")
    assert methodology.check_id_uniqueness_errors([a, b]) == []


# --- determinism -------------------------------------------------------------


def test_manifest_digest_is_deterministic() -> None:
    assert methodology.manifest_digest() == methodology.manifest_digest()


def test_manifest_digest_is_order_independent() -> None:
    shuffled = list(reversed(ALL_CHECKS))
    assert shuffled != ALL_CHECKS  # sanity: the shuffle actually changed order
    assert methodology.manifest_digest(shuffled) == methodology.manifest_digest(ALL_CHECKS)
    assert methodology.manifest(shuffled) == methodology.manifest(ALL_CHECKS)


# --- SPEC_VERSION agreement with the vendored schema and PROVENANCE.md -----


def _provenance_text() -> str:
    return resources.files("a2a_scorecard.vendor").joinpath("PROVENANCE.md").read_text()


def test_spec_version_matches_schema_resource_filename() -> None:
    match = re.search(r"v\d+\.\d+\.\d+", schema.SCHEMA_RESOURCE)
    assert match is not None, f"could not find a version in {schema.SCHEMA_RESOURCE!r}"
    assert match.group(0) == schema.SPEC_VERSION


def test_spec_version_matches_provenance_md() -> None:
    text = _provenance_text()
    # PROVENANCE.md is a markdown table; find the row for SCHEMA_RESOURCE
    # and read its Version column, rather than hardcoding an expected
    # string, so this test fails if the vendored spec is bumped without
    # updating SPEC_VERSION.
    row_match = None
    for line in text.splitlines():
        if line.strip().startswith("|") and schema.SCHEMA_RESOURCE in line:
            row_match = line
            break
    assert row_match is not None, f"no PROVENANCE.md table row mentions {schema.SCHEMA_RESOURCE!r}"
    version_match = re.search(r"v\d+\.\d+\.\d+", row_match)
    assert version_match is not None, f"no version token found in row: {row_match!r}"
    assert version_match.group(0) == schema.SPEC_VERSION
