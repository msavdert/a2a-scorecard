"""Command-line interface: a2a-scorecard scan <url> [--json] [--allow-http]."""

from __future__ import annotations

import argparse
import json
import sys

import a2a_scorecard
from a2a_scorecard.config import Settings
from a2a_scorecard.models import TargetReport
from a2a_scorecard.scan import run_scan


def _render_text(report: TargetReport) -> str:
    lines = [
        f"target:  {report.target}",
        f"scanned: {report.scanned_at} "
        f"(scanner {report.scanner_version}, grading v{report.grading_version})",
        f"card generation: {report.spec_generation}",
        "",
    ]
    for r in report.results:
        lines.append(f"  [{r.status.value.upper():7}] {r.check_id} {r.title}")
        if r.evidence:
            lines.append(f"            {r.evidence}")
    lines += ["", f"score: {report.score}   grade: {report.grade}"]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="a2a-scorecard",
        description="Independent conformance scanner for A2A protocol endpoints.",
    )
    parser.add_argument("--version", action="version", version=a2a_scorecard.__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    scan_p = sub.add_parser("scan", help="scan one or more A2A endpoints")
    scan_p.add_argument("urls", nargs="+", help="base URL(s) of the agent endpoint(s)")
    scan_p.add_argument("--json", action="store_true", help="emit JSON reports")
    scan_p.add_argument("--timeout", type=float, default=10.0, help="per-request timeout seconds")
    scan_p.add_argument(
        "--allow-http",
        action="store_true",
        help="do not degrade plain-http targets (local development only)",
    )
    args = parser.parse_args(argv)

    settings = Settings(timeout_s=args.timeout, allow_http=args.allow_http)
    reports = [run_scan(url, settings) for url in args.urls]
    if args.json:
        print(json.dumps([r.to_dict() for r in reports], indent=2))
    else:
        print("\n\n".join(_render_text(r) for r in reports))
    return 0


if __name__ == "__main__":
    sys.exit(main())
