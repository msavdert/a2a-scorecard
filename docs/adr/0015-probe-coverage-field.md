# ADR-0015: Reports carry probe coverage alongside the grade

Date: 2026-08-22. Status: accepted.

## Context

ADR-0005 excludes SKIP from both sides of the score, so a target is
graded only on what applies to it. The tier-2 v0.2 milestone review
quantified the consequence: a gRPC-only agent with a clean card can
score 100/A on 60 of 160 total check weight without its message
handling ever being probed, and an auth-gated agent can land in the
A range even though the scanner could not verify it answers at all. A
grade alone therefore overstates what was measured for narrow or
gated targets - exactly the kind of silent overstatement that erodes
the credibility ADR-0001 names as the core asset.

## Decision

- Every report carries two new informational fields next to the score:
  `applicable_weight` (sum of the weights of non-SKIP results, the
  denominator the score was actually computed over) and `max_weight`
  (sum of the weights of all registered checks at scan time).
- The text report renders them as "graded on N of M check weight";
  JSON carries both numbers so the dataset and the future scorecard
  can compute coverage.
- The scorecard site (v0.4) must display coverage with the grade; the
  ROADMAP v0.4 milestone inherits this as a requirement. Two targets
  with the same letter but different coverage must be visually
  distinguishable.
- The score and letter grade themselves are unchanged, so
  GRADING_VERSION stays "1" (ADR-0011: the trigger is a change to a
  released grade, and this changes none).
- Deliberately deferred: any minimum-coverage gate on letter grades
  (for example, capping at B when message handling was never probed).
  That would change released grades, so it needs its own ADR and a
  GRADING_VERSION bump, and is best decided against real v0.3 dataset
  distributions rather than guessed now.

## Rationale

The honest fix for "graded on little" is to say so, not to punish it:
an auth-gated agent is behaving legally (ADR-0005's judgment call),
and a gRPC-only agent cannot help that we lack a gRPC probe. Coverage
makes the measurement's breadth part of the public record, keeps the
scoring math untouched and reproducible, and gives the deferred
minimum-coverage debate the data it needs.

## Consequences

- `TargetReport` gains `applicable_weight` and `max_weight`; tests pin
  their arithmetic against the fixture scans.
- The v0.3 dataset schema includes both fields from its first record,
  avoiding a backfill later.
