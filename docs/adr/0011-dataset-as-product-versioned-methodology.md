# ADR-0011: The dataset is the product; grades carry a methodology version

Date: 2026-08-21. Status: accepted.

## Decision

- The append-only scan dataset (ROADMAP v0.3) is the project's primary
  long-term product. The scanner is the instrument; the neutral,
  longitudinal record of how the A2A ecosystem actually behaves is the
  asset that cannot be reproduced by anyone starting later.
- Every graded report carries an explicit `grading_version` field next
  to the existing `scanner_version`, starting at `"1"`. It identifies
  the grading methodology: the set of checks, their weights, the
  status-to-earned mapping, and the letter bands.
- `grading_version` increments only when a released grade for an
  unchanged target could change: adding or retiring a check, changing
  a weight, changing earned values or letter bands. Bug fixes that
  restore documented behavior do not increment it. Because check IDs
  are permanent (CLAUDE.md rule 3), a methodology version plus the
  per-check results fully explains any historical grade.
- Every v0.3 dataset record is stamped with `scanner_version`,
  `grading_version`, and the vendored spec version, so trend analysis
  can distinguish "the ecosystem got better" from "the ruler changed".
- Pre-release (until v0.4 launch), `grading_version` stays `"1"` while
  the v0.2 check suite grows: nothing has been published, so there is
  no released grade to protect. The first public dataset freezes
  methodology version 1; from then on the increment rule above is
  binding.

## Rationale

A scorecard that cannot answer "why did my grade change?" burns the
credibility that ADR-0001 names as the project's core asset. SSL Labs
survived years of methodology evolution by versioning its grading
criteria; the cheap moment to adopt the same discipline is before the
first grade is public. Making the dataset the declared product also
sets design priorities for v0.3: record format stability and
provenance beat scanner features.

## Consequences

- `TargetReport` gains a `grading_version` field (JSON and text
  reports); tests pin its presence and current value.
- Changing grading now means: new ADR (rule 4), and a
  `grading_version` bump when the change hits released grades.
- The v0.5 "State of the ecosystem" report and any badge endpoint must
  display or embed the methodology version they were computed under.
