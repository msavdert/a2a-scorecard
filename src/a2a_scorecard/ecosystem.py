"""Aggregate ecosystem report generation (ADR-0022, ADR-0018, ADR-0017).

`aggregate()` is a pure function from parsed dataset run files
(`dataset.RunFile`) to an `EcosystemStats` snapshot; `render_markdown()`
turns that snapshot into `docs/ECOSYSTEM.md`. Both are deliberately kept
free of I/O and randomness so the same dataset always produces the same
report - it is regenerated and committed by an unattended cron job
(ADR-0022), and a churning diff on unchanged input would be noise.

Two hard constraints from the ADRs shape every design choice here:

- **Aggregate only, ever (ADR-0018).** Nothing in this module may accept
  or emit an individual target URL, hostname, or operator name. Only
  counts, ratios, check ids/titles, grade letters and spec generations
  leave this module.
- **Every figure carries its denominator (ADR-0022).** `Ratio` is the one
  type used for every statistic in `EcosystemStats`; there is no method
  anywhere in this module that returns a bare percentage. `Ratio.render()`
  always prints "n/d (x%) of <scope>", so a caller cannot show the
  percentage without the n next to it.

Grades are never pooled across `spec_generation` (ADR-0017 rule 4), and
`NG` ("not graded") is always its own bucket, never folded into F - it
means the scan did not measure enough to grade, not that the target
failed.
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from a2a_scorecard.batch import BatchOutcome
from a2a_scorecard.dataset import RunFile

# --- scope conditions ------------------------------------------------------
#
# These constants spell out, in code, exactly what "reachable" and
# "scannable" mean, because the census's headline lesson (docs/adr/0022,
# "The aggregate report is regenerated...") is that an unstated scope is
# how a true claim about a subset gets misquoted as a claim about the
# whole population.

# "Reachable": C001 (Endpoint reachable over HTTPS) concluded PASS (served
# over TLS) or WARN (served over plain HTTP but still answered, when the
# scanner's settings allow inspecting it). Anything else - FAIL, BLOCKED,
# ERROR - means the connection itself did not succeed.
REACHABLE_CHECK_ID = "C001"
_REACHABLE_STATUSES = frozenset({"pass", "warn"})

# "Scannable": C011 (Agent Card is valid JSON) concluded PASS. Deliberately
# narrower than "reachable": an endpoint can answer HTTP and still serve no
# card at all, or one that is not valid JSON. C011 is chosen over C010
# (card present) because "scannable" means the scanner could actually parse
# something to grade, and over C012 (schema-valid) because a structurally
# invalid-but-parseable card is exactly the kind of target this report
# needs to be able to count and describe, not define out of existence.
SCANNABLE_CHECK_ID = "C011"
_SCANNABLE_STATUSES = frozenset({"pass"})

# C010 (Agent Card served at well-known URI): PASS means the modern
# /.well-known/agent-card.json path answered; WARN means only the
# pre-v0.3.0 legacy /.well-known/agent.json path did (see
# checks/agent_card.py). Both count as "card present".
CARD_LOCATION_CHECK_ID = "C010"

# C020 is the only check that ever sets details.auth_required (protocol.py):
# it is set the moment a probe hits 401/403, which is also where
# ctx.auth_gated is latched for the rest of the scan. TargetReport does not
# carry auth_gated directly, so this is read back out of C020's result.
_AUTH_CHECK_ID = "C020"
_AUTH_DETAIL_KEY = "auth_required"

# Conditional protocol/posture checks the report gives an explicit pass
# rate for. Each is heavily SKIP-populated by design (most cards do not
# declare streaming, REST, or a signature), so the pass rate is always
# reported over the applicable (non-SKIP) subset, never over every scan.
TLS_CHECK_ID = "C032"
SIGNATURE_CHECK_ID = "C031"
STREAMING_CHECK_ID = "C022"
REST_CHECK_ID = "C023"

_ABSENCE_OUTCOMES: tuple[str, ...] = tuple(
    o.value for o in BatchOutcome if o is not BatchOutcome.OK
)
_ALL_OUTCOMES: tuple[str, ...] = (*_ABSENCE_OUTCOMES, BatchOutcome.OK.value)

_GRADE_LABELS: tuple[str, ...] = ("A", "B", "C", "D", "F", "NG")


# --- the one statistic type -------------------------------------------------


@dataclass(frozen=True)
class Ratio:
    """A count out of a denominator, with the scope that denominator means.

    This is the only shape a statistic takes anywhere in this module.
    There is deliberately no method that returns a bare float or percentage
    string on its own - `render()` always prints the numerator and
    denominator alongside the percentage, so a caller physically cannot
    show one without the other.
    """

    numerator: int
    denominator: int
    scope: str

    def fraction(self) -> float | None:
        """The raw fraction, or None if the denominator is zero. Exposed
        for callers that need to sort or threshold; never call this to
        produce display text - use `render()`, which keeps the n visible."""
        if self.denominator == 0:
            return None
        return self.numerator / self.denominator

    def render(self) -> str:
        if self.denominator == 0:
            return f"0/0 (n/a) of {self.scope}"
        pct = 100.0 * self.numerator / self.denominator
        return f"{self.numerator}/{self.denominator} ({pct:.1f}%) of {self.scope}"


@dataclass(frozen=True)
class CoverageDistribution:
    """Median/quartiles of probe coverage (applicable_weight / max_weight,
    ADR-0015) over the scanned population the figure is computed over."""

    n: int
    median: float | None
    q1: float | None
    q3: float | None

    @classmethod
    def from_values(cls, values: Sequence[float]) -> CoverageDistribution:
        ordered = sorted(values)
        n = len(ordered)
        if n == 0:
            return cls(n=0, median=None, q1=None, q3=None)
        if n == 1:
            only = ordered[0]
            return cls(n=1, median=only, q1=only, q3=only)
        q1, _, q3 = statistics.quantiles(ordered, n=4, method="inclusive")
        return cls(n=n, median=statistics.median(ordered), q1=q1, q3=q3)


@dataclass(frozen=True)
class CheckDistribution:
    """Status counts for one check, each carrying its own denominator."""

    check_id: str
    title: str
    statuses: dict[str, Ratio]


# --- the aggregate snapshot --------------------------------------------------


@dataclass(frozen=True)
class EcosystemStats:
    """A capped, aggregate-only snapshot of the dataset. Never carries a
    target URL, hostname, or operator name (ADR-0018)."""

    per_operator_cap: int

    # Target-record counts: raw is every distinct target_id in the dataset
    # (across all run files given), capped is what the figures below are
    # actually computed over. Reporting both keeps the cap's effect visible
    # (docs/adr/0022, "The dataset is complete; the report is capped").
    raw_n: int
    capped_n: int
    operators_in_capped_n: int

    # Every record in the capped set, including absences (excluded,
    # throttled, skipped, errored) - denominator is capped_n.
    outcome_counts: dict[str, Ratio]

    # Denominator for these and everything below is `scanned_n`: capped
    # records whose outcome was OK and therefore carry a report. Absences
    # are never counted as scanned results.
    scanned_n: int
    reachable: Ratio
    scannable: Ratio

    # Stratified by spec_generation; never pooled (ADR-0017 rule 4). Each
    # inner Ratio's denominator is that generation's own scanned count, not
    # the whole scanned population.
    grade_distribution: dict[str, dict[str, Ratio]]
    spec_generation_distribution: dict[str, Ratio]

    check_status_distribution: dict[str, CheckDistribution]

    card_location: dict[str, Ratio]
    auth_gated: Ratio

    tls_pass_rate: Ratio
    signature_pass_rate: Ratio
    streaming_pass_rate: Ratio
    rest_pass_rate: Ratio

    coverage: CoverageDistribution

    # Provenance collected from the run file headers that were aggregated,
    # kept on the stats object so a caller building its own report text
    # (or a test) does not have to re-open the run files.
    run_ids: tuple[str, ...] = field(default_factory=tuple)
    scanner_versions: tuple[str, ...] = field(default_factory=tuple)
    grading_versions: tuple[str, ...] = field(default_factory=tuple)
    spec_versions: tuple[str, ...] = field(default_factory=tuple)
    grading_manifest_digests: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Provenance:
    """What ruler the report was generated under: which run(s), and which
    scanner/grading/spec versions and grading-manifest digest they were
    stamped with. Kept distinct from `EcosystemStats` so a caller can pass
    provenance assembled from context the dataset itself doesn't carry
    (e.g. the workflow run that produced it) without threading it through
    `aggregate()`."""

    run_ids: tuple[str, ...]
    scanner_versions: tuple[str, ...]
    grading_versions: tuple[str, ...]
    spec_versions: tuple[str, ...]
    grading_manifest_digests: tuple[str, ...]

    @classmethod
    def from_run_files(cls, run_files: Sequence[RunFile]) -> Provenance:
        return cls(
            run_ids=_sorted_header_values(run_files, "run_id"),
            scanner_versions=_sorted_header_values(run_files, "scanner_version"),
            grading_versions=_sorted_header_values(run_files, "grading_version"),
            spec_versions=_sorted_header_values(run_files, "spec_version"),
            grading_manifest_digests=_sorted_header_values(run_files, "grading_manifest_digest"),
        )


def _sorted_header_values(run_files: Sequence[RunFile], key: str) -> tuple[str, ...]:
    values = {rf.header[key] for rf in run_files if rf.header and rf.header.get(key) is not None}
    return tuple(sorted(values))


# --- aggregate() -------------------------------------------------------------


def _latest_per_target(run_files: Sequence[RunFile]) -> list[dict[str, Any]]:
    """One row per target_id: the most recent record across every run file
    given, by `started_at`. Mirrors `dataset.rebuild_index`'s
    `last_scanned_at` logic, since the dataset accumulates one row per scan
    per target over many monthly runs and the report describes the current
    state, not the scan history."""
    latest: dict[str, dict[str, Any]] = {}
    for run_file in run_files:
        for row in run_file.targets:
            target_id = row.get("target_id")
            if not target_id:
                continue
            current = latest.get(target_id)
            if current is None or row.get("started_at", "") >= current.get("started_at", ""):
                latest[target_id] = row
    return [latest[key] for key in sorted(latest)]


def _select_capped(rows: list[dict[str, Any]], per_operator_cap: int) -> list[dict[str, Any]]:
    """At most `per_operator_cap` rows per operator, chosen deterministically
    by sorting each operator's rows by target_id and taking the first N -
    so the same dataset always yields the same capped set regardless of the
    order records were read in (docs/adr/0022)."""
    by_operator: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_operator[row["operator"]].append(row)
    capped: list[dict[str, Any]] = []
    for operator in sorted(by_operator):
        members = sorted(by_operator[operator], key=lambda r: r["target_id"])
        capped.extend(members[:per_operator_cap])
    capped.sort(key=lambda r: r["target_id"])
    return capped


def _check_result(row: dict[str, Any], check_id: str) -> dict[str, Any] | None:
    report: dict[str, Any] | None = row.get("report")
    if not report:
        return None
    for result in report.get("results", ()):
        if result.get("check_id") == check_id:
            return dict(result)
    return None


def _check_status(row: dict[str, Any], check_id: str) -> str | None:
    result = _check_result(row, check_id)
    return result.get("status") if result is not None else None


def _pass_rate(rows: Sequence[dict[str, Any]], check_id: str) -> Ratio:
    """PASS / (every non-SKIP conclusion) for one conditional check. SKIP is
    excluded from the denominator because it means the check did not apply
    (e.g. a card that declares no streaming capability), not that it was
    attempted and failed - the same principle grading.py applies to scoring."""
    applicable = 0
    passed = 0
    for row in rows:
        status = _check_status(row, check_id)
        if status is None or status == "skip":
            continue
        applicable += 1
        if status == "pass":
            passed += 1
    return Ratio(passed, applicable, f"capped scans where {check_id} was applicable (non-SKIP)")


def aggregate(run_files: Iterable[RunFile], *, per_operator_cap: int = 2) -> EcosystemStats:
    """Build an `EcosystemStats` snapshot from parsed dataset run files.

    Pure and deterministic: the same `run_files` content (in any order)
    always produces an equal `EcosystemStats`, which is what lets
    `render_markdown` be byte-identical across regenerations of an
    unchanged dataset.
    """
    run_file_list = list(run_files)
    all_rows = _latest_per_target(run_file_list)
    raw_n = len(all_rows)

    capped_rows = _select_capped(all_rows, per_operator_cap)
    capped_n = len(capped_rows)
    operators_in_capped_n = len({row["operator"] for row in capped_rows})

    outcome_counts = {
        outcome: Ratio(
            sum(1 for row in capped_rows if row.get("outcome") == outcome),
            capped_n,
            "capped target records",
        )
        for outcome in _ALL_OUTCOMES
    }

    # Absences never count as scanned results: only OK rows with an actual
    # report contribute to anything below this point.
    scanned_rows = [
        row
        for row in capped_rows
        if row.get("outcome") == BatchOutcome.OK.value and row.get("report")
    ]
    scanned_n = len(scanned_rows)

    reachable_n = sum(
        1 for row in scanned_rows if _check_status(row, REACHABLE_CHECK_ID) in _REACHABLE_STATUSES
    )
    scannable_n = sum(
        1 for row in scanned_rows if _check_status(row, SCANNABLE_CHECK_ID) in _SCANNABLE_STATUSES
    )
    reachable = Ratio(reachable_n, scanned_n, "capped scanned targets")
    scannable = Ratio(scannable_n, scanned_n, "capped scanned targets")

    # Grades: stratified by spec_generation, never pooled (ADR-0017 rule 4).
    by_generation: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in scanned_rows:
        generation = row["report"].get("spec_generation", "undetermined")
        by_generation[generation].append(row)

    grade_distribution: dict[str, dict[str, Ratio]] = {}
    spec_generation_distribution: dict[str, Ratio] = {}
    for generation in sorted(by_generation):
        rows = by_generation[generation]
        denom = len(rows)
        spec_generation_distribution[generation] = Ratio(denom, scanned_n, "capped scanned targets")
        grade_counts = Counter(row["report"].get("grade", "NG") for row in rows)
        grade_distribution[generation] = {
            grade: Ratio(grade_counts.get(grade, 0), denom, f"capped {generation} scans")
            for grade in _GRADE_LABELS
        }

    # Per-check status distribution, over whatever check_ids actually
    # appear in the scanned rows (not a hardcoded list), so a check
    # retirement or addition (CLAUDE.md rule 3) needs no change here.
    check_titles: dict[str, str] = {}
    check_status_counts: dict[str, Counter[str]] = defaultdict(Counter)
    for row in scanned_rows:
        for result in row["report"].get("results", ()):
            check_id = result["check_id"]
            check_titles.setdefault(check_id, result["title"])
            check_status_counts[check_id][result["status"]] += 1
    check_status_distribution = {
        check_id: CheckDistribution(
            check_id=check_id,
            title=check_titles[check_id],
            statuses={
                status: Ratio(count, scanned_n, "capped scanned targets")
                for status, count in sorted(check_status_counts[check_id].items())
            },
        )
        for check_id in sorted(check_status_counts)
    }

    card_present_n = sum(
        1 for row in scanned_rows if _check_status(row, CARD_LOCATION_CHECK_ID) in ("pass", "warn")
    )
    well_known_n = sum(
        1 for row in scanned_rows if _check_status(row, CARD_LOCATION_CHECK_ID) == "pass"
    )
    legacy_n = sum(
        1 for row in scanned_rows if _check_status(row, CARD_LOCATION_CHECK_ID) == "warn"
    )
    card_location = {
        "well_known": Ratio(well_known_n, card_present_n, "capped targets with a card present"),
        "legacy": Ratio(legacy_n, card_present_n, "capped targets with a card present"),
    }

    auth_gated_n = sum(
        1
        for row in scanned_rows
        if bool((_check_result(row, _AUTH_CHECK_ID) or {}).get("details", {}).get(_AUTH_DETAIL_KEY))
    )
    auth_gated = Ratio(auth_gated_n, scanned_n, "capped scanned targets")

    tls_pass_rate = _pass_rate(scanned_rows, TLS_CHECK_ID)
    signature_pass_rate = _pass_rate(scanned_rows, SIGNATURE_CHECK_ID)
    streaming_pass_rate = _pass_rate(scanned_rows, STREAMING_CHECK_ID)
    rest_pass_rate = _pass_rate(scanned_rows, REST_CHECK_ID)

    coverage_values = [
        row["report"]["applicable_weight"] / row["report"]["max_weight"]
        for row in scanned_rows
        if row["report"].get("max_weight")
    ]
    coverage = CoverageDistribution.from_values(coverage_values)

    provenance = Provenance.from_run_files(run_file_list)

    return EcosystemStats(
        per_operator_cap=per_operator_cap,
        raw_n=raw_n,
        capped_n=capped_n,
        operators_in_capped_n=operators_in_capped_n,
        outcome_counts=outcome_counts,
        scanned_n=scanned_n,
        reachable=reachable,
        scannable=scannable,
        grade_distribution=grade_distribution,
        spec_generation_distribution=spec_generation_distribution,
        check_status_distribution=check_status_distribution,
        card_location=card_location,
        auth_gated=auth_gated,
        tls_pass_rate=tls_pass_rate,
        signature_pass_rate=signature_pass_rate,
        streaming_pass_rate=streaming_pass_rate,
        rest_pass_rate=rest_pass_rate,
        coverage=coverage,
        run_ids=provenance.run_ids,
        scanner_versions=provenance.scanner_versions,
        grading_versions=provenance.grading_versions,
        spec_versions=provenance.spec_versions,
        grading_manifest_digests=provenance.grading_manifest_digests,
    )


# --- render_markdown() -------------------------------------------------------


def _iso(dt: datetime) -> str:
    """ISO-8601 rendering with no local-timezone dependence, so the same
    `generated_at` always renders identically regardless of the machine
    running the report (determinism, ADR-0022)."""
    return dt.isoformat(timespec="seconds")


def _fmt_list(values: Sequence[str]) -> str:
    return ", ".join(values) if values else "unknown"


def _fmt_coverage(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def render_markdown(
    stats: EcosystemStats, *, generated_at: datetime, provenance: Provenance
) -> str:
    """Render `stats` as the `docs/ECOSYSTEM.md` body. Deterministic: the
    same arguments always produce the same string, byte for byte - this is
    committed by a cron job (ADR-0022) and must not churn on an unchanged
    dataset. Names no individual operator or target, ever (ADR-0018)."""
    lines: list[str] = []
    out = lines.append

    out("# A2A ecosystem report")
    out("")
    out(
        "Aggregate measurement only. No individual operator or target is "
        "named anywhere in this report - see ADR-0018. Per-target results "
        "remain available in the published dataset for anyone who wants to "
        "reproduce these figures or recompute them under a different "
        "operator cap."
    )
    out("")
    out(f"Generated: {_iso(generated_at)}")
    out("")
    out("## Provenance")
    out("")
    out(f"- Run(s): {_fmt_list(provenance.run_ids)}")
    out(f"- Scanner version(s): {_fmt_list(provenance.scanner_versions)}")
    out(f"- Grading version(s): {_fmt_list(provenance.grading_versions)}")
    out(f"- Spec version(s): {_fmt_list(provenance.spec_versions)}")
    out(f"- Grading manifest digest(s): {_fmt_list(provenance.grading_manifest_digests)}")
    out("")
    out("## Population and the operator cap")
    out("")
    out(f"- Dataset holds {stats.raw_n} target record(s) (raw n, uncapped).")
    out(
        f"- This report is computed over at most {stats.per_operator_cap} "
        f"record(s) per operator: {stats.capped_n} target record(s) "
        f"(capped n) across {stats.operators_in_capped_n} operator(s)."
    )
    out(
        "- The cap exists because the raw dataset has a long operator tail "
        "(a handful of operators run dozens to over a hundred subdomains "
        "each); without it, the figures below would describe those "
        "operators rather than the ecosystem. See ADR-0022."
    )
    out("")
    out("## Outcomes (capped dataset)")
    out("")
    out(
        "Every capped target record, including absences. Absences "
        "(excluded, throttled, skipped, errored, budget/deadline-exceeded) "
        "are not scan results and are never counted as failures below."
    )
    out("")
    for outcome in _ALL_OUTCOMES:
        out(f"- `{outcome}`: {stats.outcome_counts[outcome].render()}")
    out("")
    out("## Reachability and scannability")
    out("")
    out(
        f"- Reachable (C001 concluded PASS or WARN - the endpoint answered "
        f"at all, over HTTPS or plain HTTP): {stats.reachable.render()}"
    )
    out(
        f"- Scannable (C011 concluded PASS - a parseable Agent Card was "
        f"served): {stats.scannable.render()}"
    )
    out("")
    out("## Spec generation")
    out("")
    for generation in sorted(stats.spec_generation_distribution):
        out(f"- `{generation}`: {stats.spec_generation_distribution[generation].render()}")
    out("")
    out("## Grade distribution (stratified by spec generation, never pooled)")
    out("")
    out(
        "ADR-0017 rule 4: grades are never pooled across spec generations, "
        "because v0.x cards are measured against a smaller rubric (they "
        "skip C012, the heaviest single check) and score better on average "
        "for that reason alone, not because they are more conformant. "
        '`NG` ("not graded") means the scan did not measure enough to '
        "grade - it is not a failing grade and is never counted as one."
    )
    out("")
    for generation in sorted(stats.grade_distribution):
        out(f"### `{generation}`")
        out("")
        for grade in _GRADE_LABELS:
            out(f"- {grade}: {stats.grade_distribution[generation][grade].render()}")
        out("")
    out("## Agent Card location")
    out("")
    well_known = stats.card_location["well_known"].render()
    legacy = stats.card_location["legacy"].render()
    out(f"- Well-known path (`/.well-known/agent-card.json`): {well_known}")
    out(f"- Legacy path (`/.well-known/agent.json`): {legacy}")
    out("")
    out("## Auth-gated endpoints")
    out("")
    out(
        f"- {stats.auth_gated.render()}. These returned 401/403 on the "
        "conformance probe and were, per policy, not probed further behind "
        "the gate."
    )
    out("")
    out("## Posture and conditional-binding pass rates")
    out("")
    out(
        "Each rate is over the subset of scans where the check applied "
        "(non-SKIP); most cards do not declare every optional feature."
    )
    out("")
    out(f"- TLS posture (C032) PASS rate: {stats.tls_pass_rate.render()}")
    out(f"- Card signature (C031) PASS rate: {stats.signature_pass_rate.render()}")
    out(f"- Streaming binding (C022) PASS rate: {stats.streaming_pass_rate.render()}")
    out(f"- REST/HTTP+JSON binding (C023) PASS rate: {stats.rest_pass_rate.render()}")
    out("")
    out("## Probe coverage distribution")
    out("")
    out(
        f"- n = {stats.coverage.n}; median coverage = "
        f"{_fmt_coverage(stats.coverage.median)}; "
        f"Q1 = {_fmt_coverage(stats.coverage.q1)}; "
        f"Q3 = {_fmt_coverage(stats.coverage.q3)}"
    )
    out(
        "- Coverage is applicable_weight / max_weight (ADR-0015): the "
        "fraction of the rubric a scan actually measured. Conditional "
        "checks (signature, security schemes, streaming, REST) SKIP on "
        "most targets by design, so coverage well below 1.0 is normal."
    )
    out("")
    out("## Per-check status distribution")
    out("")
    for check_id in sorted(stats.check_status_distribution):
        dist = stats.check_status_distribution[check_id]
        out(f"### {check_id} - {dist.title}")
        out("")
        for status in sorted(dist.statuses):
            out(f"- `{status}`: {dist.statuses[status].render()}")
        out("")
    out("## Limitations")
    out("")
    out(
        "- **Selection bias runs upward.** Most candidate targets come "
        "from directories that health-check their own listings before "
        "publishing them, so this population skews toward endpoints that "
        "were already known to answer. Nothing here corrects for that."
    )
    out(
        "- **This is the indie long tail, not enterprise deployments.** "
        "Publicly discoverable A2A endpoints skew toward solo builders, "
        "brokers, and single-page deployments. Enterprise adopters "
        "typically sit behind authentication and inside private networks, "
        "which a public scanner structurally cannot see (ADR-0018)."
    )
    out(
        "- Figures describe the capped, scannable-where-stated subset, not "
        "the A2A ecosystem as a whole. Every figure above states its own "
        "denominator for exactly this reason."
    )
    out("")

    return "\n".join(lines) + "\n"


def write_report(
    run_files: Iterable[RunFile],
    path: str | Path,
    *,
    per_operator_cap: int = 2,
    generated_at: datetime,
) -> EcosystemStats:
    """Aggregate `run_files` and write the rendered report to `path`.

    Returns the `EcosystemStats` so a caller (the CLI's `report`
    subcommand, or a test) can inspect the figures without re-parsing the
    file it just wrote.
    """
    run_file_list = list(run_files)
    stats = aggregate(run_file_list, per_operator_cap=per_operator_cap)
    provenance = Provenance.from_run_files(run_file_list)
    text = render_markdown(stats, generated_at=generated_at, provenance=provenance)
    Path(path).write_text(text, encoding="utf-8")
    return stats
