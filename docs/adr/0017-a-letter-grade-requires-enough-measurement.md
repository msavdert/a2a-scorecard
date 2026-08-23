# ADR-0017: A letter grade requires enough measurement to support it

Date: 2026-08-22. Status: accepted.
Answers the question ADR-0015 deferred. Amends ADR-0005's grading semantics.

## Context

ADR-0005 excludes SKIP from both sides of the score so that a target is
graded only on what applies to it. ADR-0015 documented the consequence,
added `applicable_weight` / `max_weight` to every report, and deferred the
harder question - whether a letter grade should be gated on coverage -
on the explicit grounds that it should be decided against real dataset
distributions rather than guessed. The 2026-08-22 census supplies those
distributions, so the question is now answerable.

Measured over the 304 scannable census targets, after the ADR-0016 fix:

- Coverage is tightly clustered: min 0.5625, median 0.6875, max 0.9375.
  Nothing reaches 1.0, because conditional checks (signature, security
  schemes, streaming, REST) skip on most targets by design.
- **Grade A correlates with being behind the spec.** 26 of 110 v0.x-
  generation targets (24%) scored in the A band, against 5 of 70
  v1-generation targets (7%). A v0.x card skips C012, the single heaviest
  card check at weight 20, so an agent on the previous generation is
  measured against a smaller rubric and clears it more easily. The tool
  validates against A2A v1.0.1 and was handing its top grade
  disproportionately to cards not written to v1.0.1.
- ADR-0015's predicted pathological case did not appear in this sample but
  is reachable: a target can be graded on 60 of 160 weight with its
  message handling never probed at all - and separately, a target whose
  bindings we have no probe for can carry coverage as high as 0.875 while
  never having been talked to. A coverage number alone does not detect
  that.

ADR-0015's answer to overstatement was to report coverage beside the
grade. That was necessary and is not sufficient: a letter travels without
its footnote. Once a grade is written into a dataset, quoted, or read
quickly, the coverage pair beside it stops accompanying it.

## Decision

The scoring math of ADR-0005 is unchanged. SKIP stays out of the
denominator; no new statuses; v0.x cards are not re-graded as failures.
What changes is when the scanner is willing to emit a **letter** at all,
and what the top letter means.

1. **Coverage floor.** If `applicable_weight / max_weight < 0.60`, no
   letter is emitted. The report carries `grade = "NG"` with
   `grade_withheld = "coverage"`, alongside the score and the coverage
   figures, which are still reported in full.

2. **Message handling must have been probed.** If neither C020 nor C023
   reached a conclusion - PASS, WARN, FAIL or BLOCKED, as opposed to SKIP,
   ERROR or absent - no letter is emitted: `grade = "NG"`,
   `grade_withheld = "unprobed"`. A conformance grade asserts something
   about how an agent behaves. If the probe was never applicable, we graded
   a document, and we should say so rather than letter-grade a JSON file.

   BLOCKED counts as a conclusion, and this was wrong in the first draft of
   this ADR. BLOCKED means a dependency of the probe failed - no card, an
   unparseable card, an unreachable host - which is a finding about the
   target, and a damning one. Excluding it made an unreachable endpoint
   report NG rather than F, which inverts the truth: a dead endpoint is the
   most conclusive measurement this scanner can make. The error only
   surfaced when the rule was wired into a real scan, because the unit
   tests constructed check lists directly and never produced the
   all-BLOCKED shape that a dead target produces.

3. **The A band additionally requires coverage >= 0.70.** A score in the A
   band with coverage below that is reported as B. Deliberately stated as a
   coverage rule rather than "C012 must have passed", so that it survives
   check retirement and addition without a special case.

   The census's v1 median coverage is 0.75, and that was the first draft's
   threshold. It is wrong for a reason the census could not show: a
   perfect, minimal v1 agent served over HTTPS - clean card, answers its
   endpoint, no signature, no streaming, no REST, no declared security
   schemes - lands on exactly 0.75. A floor at its exact coverage leaves it
   one newly added conditional check away from losing its A through no
   change of its own. On the census sample 0.70 and 0.75 select the
   identical set of A grades, so the margin is free.

   The underlying fragility does not disappear at 0.70: coverage is a
   fraction of the live `max_weight`, so adding checks lowers everyone's
   coverage. That is contained rather than solved, by the ADR-0021
   manifest digest - any change to the check set trips the CI guard, which
   forces a GRADING_VERSION bump and, with it, a re-evaluation of these
   thresholds against the then-current distribution. The thresholds are
   part of the methodology, not constants that quietly outlive it.

`NG` is not a failing grade and must never be rendered or aggregated as
one. It means the scan did not measure enough to grade. Reports, the
dataset and the aggregate report all keep NG in its own category.

4. **The aggregate report never pools generations.** Any published grade
   distribution is stratified by `spec_generation`. This is where the
   inverted incentive is actually neutralised: rules 1-3 stop an
   individual grade from overstating, but only stratification stops
   "v0.x agents score better" from reading as "v0.x agents are better"
   in the one place this project now publishes comparisons (ADR-0018).

## Effect on the census sample (n=304)

| | A | B | C | D | F | NG |
| --- | --- | --- | --- | --- | --- | --- |
| ADR-0016 fix only | 31 | 32 | 32 | 199 | 10 | - |
| plus this ADR | 3 | 40 | 14 | 199 | 10 | 38 |

All 3 remaining A grades are v1-generation. All 26 v0.x A grades are
demoted to B by rule 3. NG is 38 (12.5%), every one of them by the
coverage floor; with BLOCKED counted as a conclusion, no target in this
sample is withheld as unprobed.

Rule 2 has become narrow, and it is worth being precise about how narrow.
ADR-0015's predicted case - a gRPC-only agent graded on 60 of 160 weight -
is caught by the coverage floor, not by rule 2, because skipping the
message probes drags coverage below 0.60 on its own. Rule 2 only fires for
a target that skips both message probes and still clears 0.60, which needs
it to run HTTPS, serve a signed card and declare security schemes: at most
105 of 160 weight, or 0.656. That target exists in principle and not in
this sample. The rule stays because the alternative is letter-grading an
agent we never exchanged a message with, and because the shape is a unit
test rather than a hope; but the coverage floor is doing essentially all
of the work on real data.

## Rationale

Grade inflation on thin evidence is the specific way a measurement project
loses the credibility ADR-0001 names as its only asset, and it is worse
than being harsh, because it is invisible to the reader. The three rules
are ordered by how directly they attack that: rule 2 catches the case
where the grade is about nothing, rule 1 catches the case where it is
about too little, rule 3 catches the case where it is about the wrong
spec generation.

Rejected alternatives:

- *Counting SKIP as unearned.* Punishes a gRPC-only agent for a probe we
  have not written, and an unsigned card for using an optional feature.
  Our gaps are not the target's defects.
- *Capping non-v1 generations directly.* Equivalent in effect here but
  couples grading to a generation label, and would need rewriting the
  first time the spec moves again. The coverage formulation is
  generation-agnostic and happens to bite the right population.
- *Relying on ADR-0015's coverage fields alone.* Tried; the census shows
  what it produces.

The thresholds 0.60 and 0.70 are fitted to one sample and this ADR does
not pretend they are laws. They are pinned to GRADING_VERSION and may only
move with a superseding ADR and a version bump, which is exactly the
machinery ADR-0011 exists to provide.

GRADING_VERSION stays "1": no dataset has been released, so no released
grade changes. It freezes with the first published dataset, and any later
change to these rules increments it.

## Consequences

- `grading.py` gains the letter-withholding logic and a `grade_withheld`
  reason; `TargetReport` carries both fields; the text report renders
  `NG (not graded: coverage 0.56 below 0.60 floor)` rather than a letter.
- Tests pin all three rules and the NG rendering, including the case that
  did not occur in the census - high coverage with no message probe.
- The dataset schema carries `grade`, `grade_withheld`, `score`,
  `applicable_weight`, `max_weight` and `spec_generation` from its first
  record.
- Anything that consumes grades must handle a non-letter value. The
  aggregate report generator treats NG as its own category.
