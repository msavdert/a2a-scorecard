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
from a2a_scorecard.transport import ScanAborted, ScanTransport

_RUNNABLE = (CheckStatus.PASS, CheckStatus.WARN)


def run_scan(
    url: str,
    settings: Settings | None = None,
    *,
    transport: ScanTransport | None = None,
) -> TargetReport:
    """Run every registered check against `url`.

    `transport` lets a caller (batch.py, or a test) supply a `ScanTransport`
    built with injected clock/sleep/pacer; when omitted, a fresh one wrapping
    real network I/O is built here so a single ad-hoc scan (the CLI's plain
    `scan` command) still gets the request budget, deadline, and per-host
    pacing "by construction" rather than only in batch mode (ADR-0020).
    """
    settings = settings or Settings()
    scan_transport = transport or ScanTransport()
    results: list[CheckResult] = []
    with httpx.Client(
        headers={"User-Agent": settings.user_agent},
        timeout=settings.timeout_s,
        follow_redirects=True,
        # Each redirect hop spends a request out of the scan's budget;
        # httpx's default of 20 exceeds the whole budget (ADR-0020).
        max_redirects=3,
        transport=scan_transport,
    ) as client:
        ctx = ProbeContext(url, client, settings, pacer=scan_transport.pacer)
        for check_cls in sorted(ALL_CHECKS, key=lambda c: (c.stage, c.check_id)):
            check = check_cls()
            dep_status = [(dep, ctx.outcomes.get(dep)) for dep in check.requires]
            blocked_on = [
                dep
                for dep, status in dep_status
                if status is not CheckStatus.SKIP and status not in _RUNNABLE
            ]
            skipped_on = [dep for dep, status in dep_status if status is CheckStatus.SKIP]
            if blocked_on:
                result = check_cls.result(
                    CheckStatus.BLOCKED,
                    evidence=f"dependency not satisfied: {', '.join(blocked_on)}",
                )
            elif skipped_on:
                # Not-applicable cascades: a SKIPped dependency must not turn
                # into a scored BLOCKED downstream (ADR-0005).
                result = check_cls.result(
                    CheckStatus.SKIP,
                    evidence=f"dependency not applicable: {', '.join(skipped_on)}",
                )
            else:
                try:
                    result = check.run(ctx)
                except ScanAborted:
                    # A throttle, budget, or deadline abort must propagate
                    # out of run_scan, not be scored. Re-raising ahead of
                    # the blanket except below is load-bearing: without it,
                    # every abort would be caught there and turned into a
                    # scored ERROR (ADR-0020).
                    raise
                except Exception as exc:  # noqa: BLE001 - a crashing check must not kill the scan
                    result = check_cls.result(CheckStatus.ERROR, evidence=f"check crashed: {exc}")
            ctx.outcomes[check.check_id] = result.status
            results.append(result)
        spec_generation = ctx.spec_generation

    value = grading.score(results)
    # graded_result applies ADR-0017 on top of the raw band: it withholds the
    # letter entirely (NG) when too little of the rubric applied or when the
    # agent was never actually probed, and holds the A band to a coverage
    # requirement. grading.grade() alone would report the raw band and
    # overstate what was measured.
    letter, withheld = grading.graded_result(results)
    return TargetReport(
        target=url,
        scanned_at=datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
        scanner_version=a2a_scorecard.__version__,
        grading_version=grading.GRADING_VERSION,
        spec_generation=spec_generation,
        results=results,
        score=value,
        grade=letter,
        grade_withheld=withheld,
        applicable_weight=grading.applicable_weight(results),
        max_weight=grading.max_weight(results),
    )
