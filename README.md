# a2a-scorecard

Independent conformance scanner for [A2A (Agent2Agent)
protocol](https://a2a-protocol.org/) endpoints, and a longitudinal public
dataset of what the A2A ecosystem actually does.

Point it at an endpoint and it tells you, with evidence, whether the agent
conforms to the A2A specification: whether its Agent Card validates
against the official schema, whether it answers a spec-conformant request
at the address its own card advertises, what its TLS posture is, and
whether its card is signed.

## What this measures that nothing else does

Public A2A directories index agents and report liveness. As of August
2026, the largest one grades agents on 30-day uptime and p95 latency, and
its API exposes no TLS field, no schema-validation result and no signature
field. The official project ships a self-run TCK and a local debugger,
both of which require you to already own the agent.

Nobody is independently measuring schema and protocol conformance, TLS
posture, or card signatures across the public population. That gap is what
this exists for.

## What it found

From a census of 400 endpoints sampled across 396 operators on 2026-08-22
(`docs/CENSUS-2026-08-22.md`), scoped to the 304 that served a parseable
Agent Card:

- **193 (63%) do not correctly answer a spec-conformant request at the
  endpoint their own card advertises.** 110 of those return something that
  is not JSON at all.
- **6 (2%) serve a signed Agent Card.**
- **70 (23%) are on the current v1 generation of the spec.**
- **55 (18%) still serve their card only at the legacy well-known path.**
- TLS posture, by contrast, is nearly universal: 301 of 304 pass.

Those figures describe agents that serve a fetchable card. Of the full
400-target sample, 78% were scannable at all - extrapolating to roughly
1,400 live, publicly scannable A2A endpoints.

Selection bias runs upward: most candidates came from directories that
health-check their own listings. And this population is the indie long
tail, not the enterprise deployments that sit behind authentication and
inside private networks.

An independent April 2026 experiment
([a2aproject/A2A#1755](https://github.com/a2aproject/A2A/issues/1755))
found 50 of 50 agents advertising A2A support failing to answer a
correctly formatted A2A request. Our 63% is measured differently and on a
much larger sample, but it points the same way.

`docs/ECOSYSTEM.md` carries the current figures, regenerated from the
dataset on every run.

## Quickstart

    make install
    uv run a2a-scorecard scan https://agent.example.com
    uv run a2a-scorecard scan https://agent.example.com --json

Sample output:

    target:  https://agent.example.com
    card generation: v1
      [PASS   ] C001 Endpoint reachable over HTTPS
      [PASS   ] C010 Agent Card served at well-known URI
      [PASS   ] C011 Agent Card is valid JSON
      [FAIL   ] C012 Agent Card validates against official v1 schema
      ...
    score: 81.8   grade: B   graded on 130 of 160 check weight

## How it grades

Checks run in stages (reachability, Agent Card, live protocol, security);
each carries a weight. PASS earns full weight, WARN half, FAIL/BLOCKED/
ERROR none. Checks that do not apply to a target are excluded from both
sides. 90+ A, 75+ B, 60+ C, 40+ D, else F.

Two things keep a letter from claiming more than was measured
(ADR-0017). A grade is **withheld entirely** - reported as `NG`, which is
not a failing grade - when less than 60% of the rubric applied, or when
the scanner never got a response out of the agent at all. And the A band
additionally requires that at least 75% of the rubric applied, because
otherwise being behind the specification raises your grade: measured on
the census, 24% of previous-generation agents landed in the A band against
7% of current-generation ones.

Every report says what it was graded on, and the published dataset carries
the full per-check result, so any grade can be recomputed and argued with.

Rationale: `docs/adr/0005-check-architecture-and-grading.md` and
`docs/adr/0017-a-letter-grade-requires-enough-measurement.md`.

## What it will not do

`docs/SCANNING-POLICY.md` is binding on the code, not advisory. A scan
sends fewer than ten requests and at most two benign `SendMessage` pings
that identify themselves as conformance probes. No exploit payloads, no
prompt injection, no auth bypass, no fuzzing. Auth-gated endpoints are
recorded as auth-gated and not probed behind the gate. Those limits are
enforced by tests, not by review.

There is deliberately no public scorecard site ranking named agents, and
no badge programme. `docs/adr/0018-retire-the-public-per-agent-scorecard.md`
explains that decision and is honest about what it does and does not
change.

## If one of these endpoints is yours

`SECURITY.md` has the short version: how to be excluded from scanning
permanently, and how to challenge a result. Both are a GitHub issue away
and neither requires you to justify yourself.

## Development

    make check   # ruff + mypy + pytest; must be green before any commit

Contributor rules and architecture: `CLAUDE.md`, `docs/adr/`.

## Independence

This project is not affiliated with, endorsed by, or connected to the A2A
project, Google, or the Linux Foundation. "A2A" is used descriptively to
identify the protocol being tested.

## License

Apache-2.0. Vendored A2A specification files are Copyright the A2A project
authors, Apache-2.0; see `src/a2a_scorecard/vendor/PROVENANCE.md` and
`NOTICE`.
