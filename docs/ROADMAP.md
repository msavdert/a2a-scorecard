# Roadmap

Each milestone has a definition of done. Do not start a milestone's work
before the previous one's gate is met, and do not skip gates.

## v0.1 - Working scanner core (this milestone)

CLI scans a single endpoint: reachability, Agent Card discovery/parse/
schema/semantics, JSON-RPC SendMessage ping, error-handling probe, graded
report (text + JSON). Vendored spec v1.0.1. Full test suite against an
in-process fake agent.

Done when: `make check` green, CLI produces a correct A-grade against the
fake compliant agent and correct F against a dead endpoint.

## v0.2 - Check suite depth

- Streaming probe (SendStreamingMessage / SSE) as a capability check.
- TLS posture basics (protocol version, certificate validity).
- Agent Card signature verification (JWS) when signatures are present.
- Security-scheme declaration sanity checks (declared vs. observed).
- REST binding probe (`POST /message:send`) for agents declaring HTTP+JSON.

Done when: each new check has tests, an ADR entry if it changes grading,
and the fake agent grows matching modes.

## v0.3 - Batch scanning and the dataset

- Target list format (YAML) with provenance for every listed endpoint.
- Batch runner honoring the scanning policy (per-host serialization, 429).
- Persistent JSON dataset of scan results (append-only, one file per run).
- Seed list harvested from public agent directories.

Done when: one command produces a dataset for 50+ public targets without
policy violations.

## v0.4 - Public launch gate

- Static scorecard site generated from the dataset (grades, trends).
- README rewritten for a public audience; SECURITY.md and opt-out process
  in place.
- License/notice review completed.
- Owner reviews results manually for false FAILs before anything goes live.

Gate: the owner explicitly approves making the repository public and
publishing the first scorecard. Until then everything stays private
(CLAUDE.md rule 10).

## v0.5 - Continuous operation

- Scheduled re-scans, historical grade tracking, badge endpoint for agent
  authors ("scored A on a2a-scorecard").
- Spec-version tracking: update vendored spec on new A2A releases via the
  PROVENANCE procedure; dual-validate during transitions.
