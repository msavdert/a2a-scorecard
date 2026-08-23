"""The dataset writer and readers (ADR-0021).

`RunWriter` implements `batch.BatchWriter` and produces one self-delimiting
JSONL file per run: a `run_start` header, one `target` record per target
(including absences), and - only on a clean finish - a `run_end` footer.

**Absence of the footer means the run is incomplete.** That is the whole
resume story: a killed or crashed run leaves a headerless-but-footerless
file, and a reader decides "is this run done" by checking for `run_end`
alone, with no side-channel. Concretely, `RunWriter.__exit__` writes the
footer only when the `with` block exits without an exception; on an
exception it closes the file handle and lets the footer stay absent. A
run that finishes its scheduling loop cleanly but did not cover every
target - the circuit breaker tripped - still gets a footer, because the
process did not crash; that case is distinguished from a normal
completion by `run_end.aborted`, which the caller sets explicitly via
`RunWriter.close(aborted=True)` (see `__exit__`'s docstring for the two
code paths). An `aborted` flag on `run_end` therefore doesn't reintroduce
a side-channel: it never substitutes for the footer, only qualifies one
that is genuinely present.

Every record is written under a lock (writer is called from worker
threads, see batch.py) and fsynced before the call returns, so a killed
process loses at most the write in flight, never an acknowledged one.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import threading
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

from a2a_scorecard import methodology
from a2a_scorecard.batch import BatchConfig, BatchRecord
from a2a_scorecard.grading import GRADING_VERSION
from a2a_scorecard.schema import SPEC_VERSION
from a2a_scorecard.targets import Exclusion, Target

from . import USER_AGENT, __version__

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_POLICY_PATH = _REPO_ROOT / "docs" / "SCANNING-POLICY.md"

DATASET_SCHEMA_VERSION = 1


# --- small helpers -----------------------------------------------------------


def _sha256_bytes(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _sha256_file(path: str | Path) -> str:
    return _sha256_bytes(Path(path).read_bytes())


def _iso_from_epoch(ts: float) -> str:
    return (
        datetime.fromtimestamp(ts, tz=UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    )


def _iso_now(now: datetime) -> str:
    return now.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def default_now() -> datetime:
    return datetime.now(UTC)


def default_git_commit() -> str:
    """Best-effort `git rev-parse HEAD`; "unknown" if it fails.

    Only invoked when no explicit `git_commit` is passed to `RunWriter`.
    Tests always pass an explicit value, so this never shells out from the
    test suite (ADR-0021's determinism requirement).
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        return result.stdout.strip()
    except Exception:  # noqa: BLE001 - a missing commit hash must not break scanning
        return "unknown"


def generate_run_id(now: datetime | None = None) -> str:
    dt = (now or default_now()).astimezone(UTC)
    return f"run-{dt.strftime('%Y%m%dT%H%M%SZ')}"


def _provenance_of(target: Target | None) -> list[dict[str, str]] | None:
    if target is None:
        return None
    return [
        {
            "directory": s.directory,
            "ref": s.ref,
            "kind": s.kind,
            "observed_at": s.observed_at,
        }
        for s in target.sources
    ]


# --- writer --------------------------------------------------------------


class RunWriter:
    """Writer for one `data/runs/run-YYYYMMDDTHHMMSSZ.jsonl` file.

    Implements `batch.BatchWriter`: pass an instance as `run_batch`'s
    `writer` argument, or call it directly with `BatchRecord`s. Use as a
    context manager so the footer is written on a clean exit and withheld
    on an exception - see the module docstring for exactly which path
    writes what.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        run_id: str | None = None,
        targets: Iterable[Target] = (),
        target_list_path: str | Path | None = None,
        exclusions: Iterable[Exclusion] = (),
        exclusions_path: str | Path | None = None,
        exclusions_applied: bool = True,
        config: BatchConfig | None = None,
        resume: bool = False,
        now: datetime | None = None,
        git_commit: str | None = None,
        policy_path: str | Path = _DEFAULT_POLICY_PATH,
    ) -> None:
        self.path = Path(path)
        started = now or default_now()
        self.run_id = run_id or generate_run_id(started)
        self._resume = resume
        self._resumed_from = self.run_id if resume else None
        self._started_at = started
        self._closed = False
        self._target_count = 0
        self._outcome_counts: dict[str, int] = {}
        self._lock = threading.Lock()

        target_list = list(targets)
        self._targets_by_id = {t.target_id: t for t in target_list}
        exclusion_list = list(exclusions)

        commit = git_commit if git_commit is not None else default_git_commit()

        self._fh: TextIO
        if resume:
            if not self.path.exists():
                raise FileNotFoundError(
                    f"resume=True but {self.path} does not exist; repair_torn_tail() and "
                    "confirm the file first"
                )
            self._fh = open(self.path, "a", encoding="utf-8")  # noqa: SIM115 - held open for object lifetime
        else:
            self._fh = open(self.path, "x", encoding="utf-8")  # noqa: SIM115 - held open for object lifetime
            header = self._build_header(
                started=started,
                commit=commit,
                target_list_path=target_list_path,
                target_entries=len(target_list),
                exclusions_path=exclusions_path,
                exclusion_entries=len(exclusion_list),
                exclusions_applied=exclusions_applied,
                config=config or BatchConfig(),
                policy_path=policy_path,
            )
            self._write_record(header)

    # -- header -------------------------------------------------------

    def _build_header(
        self,
        *,
        started: datetime,
        commit: str,
        target_list_path: str | Path | None,
        target_entries: int,
        exclusions_path: str | Path | None,
        exclusion_entries: int,
        exclusions_applied: bool,
        config: BatchConfig,
        policy_path: str | Path,
    ) -> dict[str, Any]:
        return {
            "record_type": "run_start",
            "schema_version": DATASET_SCHEMA_VERSION,
            "run_id": self.run_id,
            "started_at": _iso_now(started),
            "scanner_version": __version__,
            "grading_version": GRADING_VERSION,
            "spec_version": SPEC_VERSION,
            "grading_manifest": methodology.manifest(),
            "grading_manifest_digest": methodology.manifest_digest(),
            "git_commit": commit,
            "user_agent": USER_AGENT,
            "policy_digest": _sha256_file(policy_path),
            "target_list": {
                "path": str(target_list_path) if target_list_path is not None else None,
                "digest": _sha256_file(target_list_path) if target_list_path is not None else None,
                "entries": target_entries,
            },
            "exclusions": {
                "path": str(exclusions_path) if exclusions_path is not None else None,
                "digest": _sha256_file(exclusions_path) if exclusions_path is not None else None,
                "entries": exclusion_entries,
                "applied": exclusions_applied,
            },
            "config": {
                "concurrency": config.concurrency,
                "within_operator_pause_s": config.within_operator_pause_s,
                "rescan_interval_s": config.rescan_interval_s,
                "circuit_breaker_threshold": config.circuit_breaker_threshold,
            },
        }

    # -- BatchWriter protocol ------------------------------------------

    def __call__(self, record: BatchRecord) -> None:
        target = self._targets_by_id.get(record.target_id)
        row = {
            "record_type": "target",
            "run_id": self.run_id,
            "target_id": record.target_id,
            "target": record.target_url,
            "operator": record.operator,
            "provenance": _provenance_of(target),
            "started_at": _iso_from_epoch(record.started_at),
            "elapsed_s": record.elapsed_s,
            "outcome": record.outcome.value,
            "error": record.error,
            "scanner_version": __version__,
            "grading_version": GRADING_VERSION,
            "spec_version": SPEC_VERSION,
            "grading_manifest_digest": methodology.manifest_digest(),
            "report": record.report.to_dict() if record.report is not None else None,
        }
        with self._lock:
            if self._closed:
                raise RuntimeError(f"RunWriter for {self.path} is already closed")
            self._write_record(row)
            self._target_count += 1
            outcome_key = record.outcome.value
            self._outcome_counts[outcome_key] = self._outcome_counts.get(outcome_key, 0) + 1

    # -- footer ---------------------------------------------------------

    def close(self, *, aborted: bool = False) -> None:
        """Write the `run_end` footer and close the file.

        Idempotent: a second call is a no-op. Call this explicitly, or
        rely on the context manager to call it on a clean exit. `aborted`
        marks a run that finished its scheduling loop (no exception) but
        did not cover every target - e.g. the circuit breaker tripped -
        as distinct from a normal completion. It is never used to paper
        over a genuinely missing footer; see the module docstring.
        """
        with self._lock:
            if self._closed:
                return
            ended = default_now()
            footer = {
                "record_type": "run_end",
                "run_id": self.run_id,
                "ended_at": _iso_now(ended),
                "wall_s": (ended - self._started_at).total_seconds(),
                "targets_attempted": self._target_count,
                "outcomes": dict(self._outcome_counts),
                "resumed_from": self._resumed_from,
                "aborted": aborted,
            }
            self._write_record(footer)
            self._closed = True
            self._fh.close()

    def _write_record(self, record: dict[str, Any]) -> None:
        line = json.dumps(record, sort_keys=True, ensure_ascii=True)
        self._fh.write(line + "\n")
        self._fh.flush()
        os.fsync(self._fh.fileno())

    # -- context manager --------------------------------------------------

    def __enter__(self) -> RunWriter:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        """Write the footer only on a clean exit.

        An exception propagating out of the `with` block means the run
        was interrupted mid-flight: the file handle is closed but
        `run_end` is deliberately never written, so the file's own
        absence of a footer is what tells a reader this run is
        incomplete - no separate "aborted" bookkeeping is needed or
        trustworthy for that case, since the crash could have happened
        before this method even ran.
        """
        if exc_type is None:
            self.close(aborted=False)
        else:
            with self._lock:
                if not self._closed:
                    self._fh.close()
                    self._closed = True
        return None


# --- readers -----------------------------------------------------------


def _iter_lines(path: str | Path) -> Iterable[str]:
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if stripped:
                yield stripped


def completed_targets(path: str | Path) -> set[str]:
    """`target_id`s already recorded in `path`, tolerating a torn tail.

    Used to build `run_batch`'s `already_done`-style skip set on resume:
    a target that already has a record in this run file - any outcome -
    must not be scanned again. The trailing line of a killed run may be a
    half-written JSON fragment; it is silently skipped rather than
    raising, since `repair_torn_tail` is the tool for actually fixing the
    file and this reader must work before that repair has run.
    """
    ids: set[str] = set()
    for line in _iter_lines(path):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("record_type") == "target":
            ids.add(record["target_id"])
    return ids


@dataclass
class RunFile:
    """The parsed contents of one run file."""

    header: dict[str, Any] | None
    targets: list[dict[str, Any]]
    footer: dict[str, Any] | None

    @property
    def complete(self) -> bool:
        return self.footer is not None


def read_run(path: str | Path) -> RunFile:
    """Parse a run file, tolerating a torn (unparseable) trailing line."""
    header: dict[str, Any] | None = None
    targets: list[dict[str, Any]] = []
    footer: dict[str, Any] | None = None
    for line in _iter_lines(path):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        record_type = record.get("record_type")
        if record_type == "run_start":
            header = record
        elif record_type == "target":
            targets.append(record)
        elif record_type == "run_end":
            footer = record
    return RunFile(header=header, targets=targets, footer=footer)


def repair_torn_tail(path: str | Path) -> int:
    """Discard a trailing unparseable line from `path`, truncating in place.

    Returns the number of bytes discarded (0 if the file was already
    clean). Truncates to the byte offset immediately after the last line
    that parses as JSON - not to a line count - so a line that is merely
    missing its terminating newline (the exact shape a killed write in
    the middle of a line leaves behind) is handled correctly too.
    """
    p = Path(path)
    data = p.read_bytes()
    good_end = 0
    for raw_line in data.splitlines(keepends=True):
        stripped = raw_line.rstrip(b"\r\n")
        if not stripped:
            good_end += len(raw_line)
            continue
        try:
            json.loads(stripped.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            break
        good_end += len(raw_line)
    discarded = len(data) - good_end
    if discarded:
        with open(p, "r+b") as fh:
            fh.truncate(good_end)
            fh.flush()
            os.fsync(fh.fileno())
    return discarded


# --- index ---------------------------------------------------------------


def rebuild_index(runs_dir: str | Path) -> dict[str, Any]:
    """Regenerate the `data/index.json` contents from every run file.

    Maps each run to its header/footer summary and computes
    `last_scanned_at` per `target_id` as the most recent `started_at`
    across every `target` record for that id, across all runs - this is
    what enforces the daily re-scan floor (ADR-0021). Runs are considered
    regardless of whether they completed (have a footer): a killed run's
    already-written target records are still real scans and must still
    count.
    """
    runs_path = Path(runs_dir)
    runs: list[dict[str, Any]] = []
    last_scanned_at: dict[str, str] = {}

    run_files = sorted(runs_path.glob("run-*.jsonl")) if runs_path.is_dir() else []

    for run_file in run_files:
        parsed = read_run(run_file)
        run_id = (
            parsed.header.get("run_id")
            if parsed.header is not None
            else (parsed.footer or {}).get("run_id", run_file.stem)
        )
        counts: dict[str, int] = {}
        for row in parsed.targets:
            outcome = row.get("outcome")
            if outcome is not None:
                counts[outcome] = counts.get(outcome, 0) + 1
            target_id = row.get("target_id")
            started_at = row.get("started_at")
            if target_id and started_at:
                current = last_scanned_at.get(target_id)
                if current is None or started_at > current:
                    last_scanned_at[target_id] = started_at

        runs.append(
            {
                "run_id": run_id,
                "path": run_file.name,
                "started_at": parsed.header.get("started_at") if parsed.header else None,
                "ended_at": parsed.footer.get("ended_at") if parsed.footer else None,
                "counts": counts,
                "digest": parsed.header.get("grading_manifest_digest") if parsed.header else None,
            }
        )

    return {
        "runs": runs,
        "last_scanned_at": last_scanned_at,
    }
