"""Report metadata pinned as public API (ADR-0011)."""

from __future__ import annotations

from typing import Any

from a2a_scorecard import grading
from a2a_scorecard.config import Settings
from a2a_scorecard.scan import run_scan

SETTINGS = Settings(allow_http=True)


def test_report_carries_grading_version(fake_agent: Any) -> None:
    report = run_scan(fake_agent("compliant"), SETTINGS)
    assert report.grading_version == grading.GRADING_VERSION
    assert report.to_dict()["grading_version"] == grading.GRADING_VERSION


def test_report_carries_probe_coverage(fake_agent: Any) -> None:
    # ADR-0015. The compliant fixture is JSON-RPC over plain http with no
    # streaming, security, or signature declarations, so C022, C023, C030,
    # C031 and C032 SKIP: 160 total weight minus 5 * 10 skipped.
    report = run_scan(fake_agent("compliant"), SETTINGS)
    assert report.max_weight == 160
    assert report.applicable_weight == 110
    data = report.to_dict()
    assert data["applicable_weight"] == 110
    assert data["max_weight"] == 160


def test_grading_version_is_frozen_at_one_pre_launch() -> None:
    # ADR-0011: stays "1" until the first public dataset freezes the
    # methodology; bumping it before then is a mistake, not a release.
    assert grading.GRADING_VERSION == "1"
