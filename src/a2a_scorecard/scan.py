"""Scan orchestrator: run all registered checks against one target."""

from __future__ import annotations

import datetime

import httpx

import a2a_scorecard
from a2a_scorecard import grading
from a2a_scorecard.checks import ALL_CHECKS
from a2a_scorecard.checks.base import ProbeContext
from a2a_scorecard.config import Settings
from a2a_scorecard.models import CheckResult, CheckStatus, TargetReport

_RUNNABLE = (CheckStatus.PASS, CheckStatus.WARN)


def run_scan(url: str, settings: Settings | None = None) -> TargetReport:
    settings = settings or Settings()
    results: list[CheckResult] = []
    with httpx.Client(
        headers={"User-Agent": settings.user_agent},
        timeout=settings.timeout_s,
        follow_redirects=True,
    ) as client:
        ctx = ProbeContext(url, client, settings)
        for check_cls in sorted(ALL_CHECKS, key=lambda c: (c.stage, c.check_id)):
            check = check_cls()
            blocked_on = [dep for dep in check.requires if ctx.outcomes.get(dep) not in _RUNNABLE]
            if blocked_on:
                result = check_cls.result(
                    CheckStatus.BLOCKED,
                    evidence=f"dependency not satisfied: {', '.join(blocked_on)}",
                )
            else:
                try:
                    result = check.run(ctx)
                except Exception as exc:  # noqa: BLE001 - a crashing check must not kill the scan
                    result = check_cls.result(CheckStatus.ERROR, evidence=f"check crashed: {exc}")
            ctx.outcomes[check.check_id] = result.status
            results.append(result)
        spec_generation = ctx.spec_generation

    value = grading.score(results)
    return TargetReport(
        target=url,
        scanned_at=datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
        scanner_version=a2a_scorecard.__version__,
        spec_generation=spec_generation,
        results=results,
        score=value,
        grade=grading.grade(value),
    )
