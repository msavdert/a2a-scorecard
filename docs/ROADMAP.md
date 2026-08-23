# Roadmap

Each milestone has a definition of done. Do not start a milestone's work
before the previous one's gate is met, and do not skip gates.

ADR-0018 changed what this project is building. The public per-agent
scorecard and the badge programme that v0.4 and v0.5 used to specify are
retired; the product is the scanner, the longitudinal dataset, and an
aggregate ecosystem report that names no individual operator. Read that
ADR before this file - the milestones below only make sense against it.

## v0.1 - Working scanner core (done)

CLI scans a single endpoint: reachability, Agent Card discovery/parse/
schema/semantics, JSON-RPC SendMessage ping, error-handling probe, graded
report (text + JSON). Vendored spec v1.0.1. Full test suite against an
in-process fake agent.

Done when: `make check` green, CLI produces a correct A-grade against the
fake compliant agent and correct F against a dead endpoint.

## v0.2 - Check suite depth (done)

- Streaming probe (SendStreamingMessage / SSE) as a capability check.
- TLS posture basics (protocol version, certificate validity).
- Agent Card signature verification (JWS) when signatures are present.
- Security-scheme declaration sanity checks (declared vs. observed).
- REST binding probe (`POST /message:send`) for agents declaring HTTP+JSON.
- Backfill of the status paths the 2026-08-21 tier-1 audit found uncovered.

Done when: each new check has tests, an ADR entry if it changes grading,
the fake agent grows matching modes, and every check status path listed
above is exercised by at least one test.

## v0.3 - A correct scanner, running unattended (this milestone)

The 2026-08-22 census found three defects that had to be fixed before any
result is worth keeping, and ADR-0018 turned the rest of the roadmap into
one goal: this has to run without a person.

Correctness first:

- Card generation inferred from structure; never a scored failure for a
  generation we could not determine (ADR-0016).
- A letter grade only where there is enough measurement to support one
  (ADR-0017).
- Correct version and a working User-Agent contact path.

Then the run loop:

- Target list (JSONL, ADR-0019) with enforced provenance for every entry,
  and a committed exclusion list honouring the policy's opt-out promise.
- Batch runner that makes the scanning policy executable: per-host
  pacing, 429 handling that never retries a POST, enforced request
  budgets, abort-and-quarantine (ADR-0020).
- Append-only dataset, one file per run, every record self-describing and
  carrying its methodology digest (ADR-0021). This is the primary
  long-term product (ADR-0011).
- Aggregate report generated from the dataset, stratified by spec
  generation, naming no operator.
- Monthly GitHub Actions run that scans, writes, regenerates and commits
  with no human in the loop (ADR-0022).

Done when: the monthly workflow completes a full run end to end, the
policy-conformance test suite passes, and the report regenerates from the
committed dataset alone.

## v0.4 - Public release

- Repository made public; README rewritten for a public audience.
- SECURITY.md, the opt-out process, and the correction path documented
  where an endpoint owner can actually find them.
- First aggregate ecosystem report published.
- License and notice review completed.
- Owner reviews the report's claims before it goes out. Every figure
  states its denominator and its scope; the census showed how easily a
  headline true of the scannable subset gets restated as a claim about
  the whole ecosystem.

No pre-notification programme, and no per-agent grade is promoted. That
obligation belonged to the retired scorecard (ADR-0018).

Gate: the owner explicitly approves publication of the repository and the
first report.

## v0.5 - Steady state

Deliberately small. The point of ADR-0018 is that this milestone costs
nearly nothing per month; if it grows, the premise is failing and the
project should be revisited rather than fed.

- Spec-version tracking: update the vendored spec on new A2A releases via
  the PROVENANCE procedure; dual-validate during transitions.
- Honour opt-out requests as they arrive.
- Periodic regeneration of the ecosystem report as the dataset grows a
  time series worth reporting on.

Not in scope, retired with ADR-0018: the scorecard site, badges, and
scheduled re-scanning framed as keeping a public ranking current.
