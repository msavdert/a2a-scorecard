# ADR-0006: Three-tier review: deterministic checks, omp audit, Claude reviewer

Date: 2026-08-21. Status: accepted.

## Context

The initial-commit review by a Claude reviewer subagent found one HIGH bug
(spec-legal gRPC-only agents were falsely failed), one policy/code drift,
and one robustness gap - clearly worth having. But premium-model review on
every commit is expensive, and the operator has off-quota capacity on
weaker models via omp.

The weaker models are unreliable at judgment (they produce plausible
wrong findings whose triage costs premium quota), but reliable at
mechanical comparison when the output format is constrained to verifiable
file:line claims.

## Decision

Split review by the kind of error it catches (docs/REVIEW-POLICY.md):

- Tier 0 (every commit, free): make check. Deterministic properties get
  encoded as tests/lints, never re-asked of a model.
- Tier 1 (per push-batch/milestone, off-quota): omp mechanical audit
  restricted to cross-checking code against ADR constants, docs, the
  vendored spec text, and test-coverage inventory. Output is claims to be
  verified, not findings.
- Tier 2 (milestone gates, grading/probe-engine changes, and the public
  launch: mandatory; otherwise not used): Claude reviewer subagent.

## Consequences

- tools/omp-audit-prompt.md is the canonical tier-1 prompt; keep it in
  sync with the file layout.
- .audit/ is gitignored scratch for tier-1 runs.
- A tier-1 run that returns advice instead of file:line claims is
  discarded, not debugged mid-milestone.
