# ADR-0012: Defer MCP expansion; keep the core protocol-neutral

Date: 2026-08-21. Status: accepted.

## Decision

- The scorecard model (independent conformance scanning plus a public,
  longitudinal dataset) plausibly applies to MCP servers, a larger
  ecosystem than A2A. We deliberately do not pursue it now.
- Until the A2A scorecard has shipped its public launch (v0.4) and
  proven continuous operation (v0.5), this project stays A2A-only. An
  MCP scorecard, if it happens, is a decision for after that - its own
  ADR, possibly its own repository.
- What we protect in the meantime is optionality, at near-zero cost:
  protocol-specific knowledge stays inside `checks/` and the vendored
  spec; the orchestrator (`scan.py`), grading (`grading.py`), report
  models (`models.py`), and the review/policy machinery remain
  protocol-neutral, as they largely already are. No abstraction layers
  are added in anticipation - the rule is only that A2A assumptions do
  not leak into the core modules.

## Rationale

Two half-built scorecards are worth less than one credible one, and
credibility is the asset (ADR-0001). The A2A niche is currently
uncontested and time-sensitive; MCP conformance is a larger but also
more crowded space where arriving later with a proven model beats
arriving early with an unproven one. Recording the deferral keeps a
future session from either drifting into premature generalization or
treating the idea as new.

## Consequences

- Code review may reject changes that put A2A-specific types or field
  names into `scan.py`, `grading.py`, or `models.py` without need.
- Nothing else changes now. Revisit after the v0.5 gate.
