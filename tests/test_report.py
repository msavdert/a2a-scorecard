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


def test_grading_version_is_frozen_at_one_pre_launch() -> None:
    # ADR-0011: stays "1" until the first public dataset freezes the
    # methodology; bumping it before then is a mistake, not a release.
    assert grading.GRADING_VERSION == "1"
