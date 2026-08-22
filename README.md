# a2a-scorecard

Independent conformance scanner and scorecard for [A2A (Agent2Agent)
protocol](https://a2a-protocol.org/) endpoints - "SSL Labs for AI agents".

Status: pre-release, private. See `docs/ROADMAP.md` for the path to a
public launch.

## Why

Agent directories are full of endpoints that advertise A2A support. In an
April 2026 experiment ([a2aproject/A2A#1755](https://github.com/a2aproject/A2A/issues/1755)),
50 out of 50 agents advertising A2A support failed to answer a correctly
formatted A2A request. There is no neutral way to tell a working agent from
a listing. This project builds one: a scanner that probes an endpoint with
benign, spec-conformant requests and grades what actually works, plus a
public scorecard of the results.

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
    score: 81.8   grade: B

## How it grades

Checks run in stages (reachability, Agent Card, live protocol); each has a
weight. PASS earns full weight, WARN half, FAIL/BLOCKED/ERROR none;
not-applicable checks are excluded. 90+ A, 75+ B, 60+ C, 40+ D, else F.
Details and rationale: `docs/adr/0005-check-architecture-and-grading.md`.

The scanner validates Agent Cards against the official JSON Schema generated
from the A2A project's `a2a.proto` (vendored at spec v1.0.1), detects
v0.x-generation agents, and probes the JSON-RPC binding with a benign
`SendMessage` ping (retried once with the legacy method name when a v1
card's endpoint rejects the v1 method). What it will never do is written
down in `docs/SCANNING-POLICY.md`.

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
