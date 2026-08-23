"""Command-line interface.

a2a-scorecard scan <url> [--json] [--allow-http]
a2a-scorecard preflight
a2a-scorecard batch --targets ... --out ...
a2a-scorecard report --runs ... --out ...
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

import a2a_scorecard
from a2a_scorecard import dataset, ecosystem, grading, preflight
from a2a_scorecard.batch import BatchConfig, run_batch
from a2a_scorecard.config import Settings
from a2a_scorecard.dataset import RunWriter, rebuild_index
from a2a_scorecard.models import TargetReport
from a2a_scorecard.scan import run_scan
from a2a_scorecard.targets import is_excluded, load_exclusions, load_targets


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
    if report.grade_withheld:
        cov = report.applicable_weight / report.max_weight if report.max_weight else 0.0
        grade_str = grading.withheld_message(report.grade_withheld, cov)
    else:
        grade_str = report.grade
    lines += [
        "",
        f"score: {report.score}   grade: {grade_str}   "
        f"(graded on {report.applicable_weight} of {report.max_weight} check weight)",
    ]
    return "\n".join(lines)


def _cmd_scan(args: argparse.Namespace) -> int:
    # An opt-out binds us here too. ADR-0019: there is no --force, because
    # "permanently" has to mean permanently for us as well.
    exclusions = load_exclusions(args.exclusions) if Path(args.exclusions).exists() else []
    for url in args.urls:
        if is_excluded(url, exclusions):
            print(f"refusing to scan {url}: excluded by {args.exclusions}", file=sys.stderr)
            return 2

    settings = Settings(timeout_s=args.timeout, allow_http=args.allow_http)
    reports = [run_scan(url, settings) for url in args.urls]
    if args.json:
        print(json.dumps([r.to_dict() for r in reports], indent=2))
    else:
        print("\n\n".join(_render_text(r) for r in reports))
    return 0


def _cmd_preflight(args: argparse.Namespace) -> int:
    try:
        url = preflight.check_contact_reachable()
    except preflight.PreflightFailed as exc:
        print(f"preflight failed: {exc}", file=sys.stderr)
        return 2
    print(f"contact path OK: {url}")
    return 0


def _iso_to_epoch(value: str) -> float | None:
    try:
        return datetime.datetime.fromisoformat(value).timestamp()
    except ValueError:
        return None


def _pick_run_path(out_dir: Path, resume_latest: bool) -> tuple[Path, bool]:
    """Return (path, resuming). A run file with no footer is an incomplete
    run and is resumed rather than abandoned (ADR-0021)."""
    if resume_latest:
        for candidate in sorted(out_dir.glob("run-*.jsonl"), reverse=True):
            if not dataset.read_run(candidate).complete:
                dataset.repair_torn_tail(candidate)
                return candidate, True
    return out_dir / f"{dataset.generate_run_id()}.jsonl", False


def _cmd_batch(args: argparse.Namespace) -> int:
    # Refuse to send anything while advertising a contact path that does not
    # resolve (ADR-0022). Not skippable: the policy requires a working
    # contact path, and the census showed what happens when nothing checks.
    try:
        preflight.check_contact_reachable()
    except preflight.PreflightFailed as exc:
        print(f"preflight failed, nothing scanned: {exc}", file=sys.stderr)
        return 2

    exclusions = load_exclusions(args.exclusions) if Path(args.exclusions).exists() else []
    targets = load_targets(args.targets)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    last_scanned: dict[str, str] = rebuild_index(out_dir).get("last_scanned_at", {})

    def already_done(target_id: str) -> float | None:
        stamp = last_scanned.get(target_id)
        return _iso_to_epoch(stamp) if stamp else None

    submitted = targets
    run_path, resuming = _pick_run_path(out_dir, args.resume_latest)
    if resuming:
        done = dataset.completed_targets(run_path)
        submitted = [t for t in targets if t.target_id not in done]
        print(f"resuming {run_path.name}: {len(done)} targets already recorded", file=sys.stderr)

    # Exclusions go to run_batch rather than being filtered out here, so an
    # excluded target still gets an `excluded` record in the dataset. The
    # opt-out then has an audit trail: "we did not scan this, and here is
    # the row that says so" (ADR-0019, ADR-0020's outcome taxonomy).
    # Filtering here instead would keep the target safe but make the
    # exclusion invisible in the dataset and permanently zero in the
    # report's excluded bucket.
    config = BatchConfig(concurrency=args.workers, exclusions=exclusions)
    with RunWriter(
        run_path,
        targets=targets,
        target_list_path=args.targets,
        exclusions=exclusions,
        exclusions_path=args.exclusions,
        config=config,
        resume=resuming,
    ) as writer:
        summary = run_batch(submitted, writer, config=config, already_done=already_done)

    # A run that measured nothing leaves no file (ADR-0024): a header and a
    # footer wrapped around zero target records is not a record of anything,
    # and committing one on every same-day re-dispatch is pure noise.
    if not dataset.read_run(run_path).targets:
        run_path.unlink(missing_ok=True)
        print("run recorded no targets; removed the empty run file", file=sys.stderr)

    index_path = out_dir.parent / "index.json"
    index_path.write_text(json.dumps(rebuild_index(out_dir), indent=2, sort_keys=True) + "\n")

    print(f"run:      {run_path}")
    print(f"targets:  {len(submitted)} submitted")
    for outcome, count in sorted(summary.outcomes.items(), key=lambda kv: kv[0].value):
        print(f"  {outcome.value:24} {count}")
    return 0


def _report_generated_at(run_files: list[dataset.RunFile]) -> datetime.datetime:
    """Timestamp the report by its newest input, not by the wall clock.

    ADR-0022 requires the report to be byte-identical for unchanged data,
    because a cron job commits it and a diff that churns on nothing is
    noise. A `datetime.now()` here defeated that: re-running the report
    produced a one-line commit every time, changing only this stamp. Dating
    it by the data also makes the stamp mean something useful - when the
    measurement was taken, rather than when the file happened to be
    rendered.
    """
    stamps = [
        str((rf.footer or {}).get("ended_at") or (rf.header or {}).get("started_at") or "")
        for rf in run_files
    ]
    newest = max((s for s in stamps if s), default="")
    if newest:
        try:
            return datetime.datetime.fromisoformat(newest)
        except ValueError:
            pass
    return datetime.datetime.now(datetime.UTC)


def _cmd_report(args: argparse.Namespace) -> int:
    runs_dir = Path(args.runs)
    run_files = [dataset.read_run(p) for p in sorted(runs_dir.glob("run-*.jsonl"))]
    if not run_files:
        print(f"no run files under {runs_dir}", file=sys.stderr)
        return 1
    ecosystem.write_report(
        run_files,
        args.out,
        generated_at=_report_generated_at(run_files),
    )
    print(f"wrote {args.out} from {len(run_files)} run file(s)")
    return 0


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
    scan_p.add_argument("--exclusions", default="data/exclusions.jsonl")
    scan_p.set_defaults(func=_cmd_scan)

    pre_p = sub.add_parser("preflight", help="check that the User-Agent contact path resolves")
    pre_p.set_defaults(func=_cmd_preflight)

    batch_p = sub.add_parser("batch", help="scan a target list into the dataset")
    batch_p.add_argument("--targets", default="data/targets.jsonl")
    batch_p.add_argument("--exclusions", default="data/exclusions.jsonl")
    batch_p.add_argument("--out", default="data/runs")
    batch_p.add_argument(
        "--resume-latest",
        action="store_true",
        help="continue the newest run file that has no footer instead of starting a new run",
    )
    batch_p.add_argument("--workers", type=int, default=8, help="concurrent operator groups (1-16)")
    # Deliberately no flag to lower the re-scan floor: policy floors are not
    # command-line arguments (ADR-0020).
    batch_p.set_defaults(func=_cmd_batch)

    report_p = sub.add_parser("report", help="regenerate the aggregate ecosystem report")
    report_p.add_argument("--runs", default="data/runs")
    report_p.add_argument("--out", default="docs/ECOSYSTEM.md")
    report_p.set_defaults(func=_cmd_report)

    args = parser.parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    sys.exit(main())
