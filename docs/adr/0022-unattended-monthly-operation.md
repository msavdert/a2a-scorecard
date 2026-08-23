# ADR-0022: Unattended monthly operation

Date: 2026-08-22. Status: accepted.
Delivers the automation ADR-0018 makes the point of the project.

## Context

ADR-0018 retired the public per-agent scorecard on the grounds that its
human obligations do not automate and scale with reach. What remains -
scanner, dataset, aggregate report - was kept precisely because it does
automate. This ADR is where that claim is cashed: if the monthly run
needs a person, ADR-0018's reasoning does not hold and the project should
have been stopped instead.

The owner instructed in this session that the project be brought to
unattended operation and left running, and granted commit and push
authority for it. That is the authorisation for a bot committing to
`main`, which CLAUDE.md rules 10 and 11 would otherwise forbid; it is
recorded here rather than inferred from an implementation.

## Decision

### A monthly GitHub Actions run, on cron and on dispatch

One workflow, `scan.yml`: monthly `schedule` plus `workflow_dispatch`, a
concurrency group so two runs never overlap, and `timeout-minutes` as a
backstop. It loads the target list, applies exclusions, scans, writes one
run file, regenerates the index and the aggregate report, and commits
with `if: always()` so a crashed run still leaves a resumable, committed
partial rather than nothing.

### The run scans the whole target list, and does not sample

The census sampled because it was a one-off question about a population
and sampling answered it at a fraction of the imposed load. A recurring
series has the opposite requirement: a fresh random draw each month
confounds real ecosystem change with sampling noise, and the trend data
is the entire reason ADR-0011 calls the dataset the product.

Scanning everything removes the confound and needs no seed to manage.
The load argument does not survive the change of cadence: monthly means
roughly twelve visits per target per year, each fewer than ten requests,
against a policy ceiling of one scan per day. The sampling code is kept
for ad-hoc research and exposed as a flag, but the automated run does not
use it.

### The dataset is complete; the report is capped per operator

Scanning everything creates a problem sampling used to hide. The target
list holds 2,479 endpoints across 1,756 operators, but the distribution
has a long head: one operator runs 112 subdomains, another 77, and the
top five account for roughly 300. An aggregate computed over raw rows
would substantially describe those five operators rather than the
ecosystem - which is precisely why the census capped its sample at two
URLs per operator.

The split: **the dataset records every target, and the report caps at two
records per operator** and states that it does. Complete data means
anyone can recompute the aggregate under a different cap, or study the
sprawl itself; a capped report means the headline figures describe
operators rather than DNS entries. Reporting both the capped n and the
raw n on every figure keeps the difference visible instead of buried in
methodology.

Wall clock for a full run is roughly 35-40 minutes at concurrency 8,
bounded below by the largest operator group, which is walked
sequentially: 112 targets at about seven seconds each is thirteen minutes
on its own. That is comfortably inside a hosted runner and needs no
sharding.

### A User-Agent contact preflight

The job fails before sending anything if the contact URL in the
User-Agent does not resolve. The policy requires a *working* contact
path, and the census sent 400 requests advertising a 404 because nothing
checked. An unattended runner cannot notice this; a preflight can. This
is the general shape the whole workflow follows - every policy line that
can be checked by a machine before the first request is checked there,
because at 03:00 there is no reviewer.

### The aggregate report is regenerated, never hand-written

`docs/ECOSYSTEM.md` is generated from the dataset each run and committed.
Constraints inherited, not restated as new policy:

- Aggregate only; no individual operator is named (ADR-0018).
- Grade distributions are stratified by `spec_generation`, and `NG` is
  reported as its own category, never as a failure (ADR-0017).
- Every figure states its denominator and its scope. The census showed
  how easily this slips: its headline claims were true of the scannable
  subset but were restated elsewhere without that scope, which is the
  difference between "two thirds of scannable agents" and "two thirds of
  A2A agents". A generator that always prints n cannot make that mistake
  once and then repeat it forever.

### Failure is not urgent, and must not become a notification habit

A failed run does not need same-day attention: the next run resumes the
partial file, and a one-month gap in a multi-year series is a gap, not a
loss. The workflow therefore does not page anyone. GitHub's default
failure email to the actor is the entire alerting design, and that is
deliberate - an unattended project that generates alerts is an attended
project with extra steps.

## Consequences

- `.github/workflows/scan.yml` plus a `report` CLI subcommand.
- The bot commit is `data/runs/<run>.jsonl`, `data/index.json` and
  `docs/ECOSYSTEM.md`, with a message naming the run id and counts.
- `ci.yml` ignores data-only commits so the bot does not trigger a full
  matrix build for a JSONL append.
- Ongoing owner cost is intended to be: nothing monthly; a vendored-spec
  update when A2A releases a new version, per `vendor/PROVENANCE.md`;
  and honouring any opt-out issue that arrives. If that set grows, the
  premise of ADR-0018 is failing and it should be revisited rather than
  absorbed.
