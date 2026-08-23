# ADR-0016: Infer Agent Card spec generation from structure, and never fail a card for a generation we could not determine

Date: 2026-08-22. Status: accepted.
Amends ADR-0005 (the C012 applicability rule). Refines ADR-0004.

## Context

`_detect_generation` (src/a2a_scorecard/checks/agent_card.py) classified a
card as v0.x only when a top-level `url` was present **and** one of
`preferredTransport` or `protocolVersion` was also present. A card carrying
`url` and declaring no version at all fell through to `unknown`, and C012
then validated it against the vendored v1.0.1 schema. The v1 AgentCard has
`"additionalProperties": false` (vendor/a2a-v1.0.1.json:86) and has no
top-level `url` (properties at vendor/a2a-v1.0.1.json:136-220), so the card
failed on a field that is correct for the generation it was actually
written to.

The 2026-08-22 census measured the blast radius: 124 of 400 targets took
this path, every one of them returned FAIL, and `url` appears in the
violation text of 111 of the 124. This was not a rare corner - it was the
single largest source of results in the whole run, and every one of them
was wrong.

The test suite did not catch it because tests/conftest.py has no
version-silent card fixture. Every card the fake agent serves declares its
generation, so the `unknown` branch was never exercised. Reality and
fixtures had diverged, which is the actual root cause; the heuristic was
merely where it surfaced.

## What the vendored spec supports

Verified against the vendored copy (v1.0.1, PROVENANCE.md:6-9), not from
memory:

- `supportedInterfaces` is a v1 AgentCard property
  (vendor/a2a-v1.0.1.json:208-213) and has no v0.x counterpart.
- `url`, `preferredTransport`, `additionalInterfaces` and a top-level
  `protocolVersion` are **not** v1 AgentCard properties. In v1
  `protocolVersion` exists only inside an AgentInterface
  (vendor/a2a-v1.0.1.json:297-300). Combined with
  `additionalProperties: false`, the presence of any of them at the top
  level is decisive: such a card cannot be a valid v1 card.
- `supportsExtendedAgentCard` moved into `capabilities.extendedAgentCard`
  in v1; the vendored spec text documents this migration explicitly
  (vendor/specification-v1.0.1.md, section A.2.2).
- The v1 AgentCard declares **no required fields**. This confirms the
  existing comment on C013 and, importantly here, means there is no field
  a v1 card must carry that could serve as a positive v1 anchor.

That last point is why "undetermined" has to survive as a real outcome. A
card with neither `supportedInterfaces` nor any v0.x-only field is
genuinely unclassifiable: it could be a minimal but valid v1 card, or a
v0.x card that omitted its interface declaration. The vendored spec offers
nothing that separates them, and we will not guess.

## Decision

1. Generation is inferred from card **structure** only, never from a
   version string a card may or may not declare:

   - Any of `supportedInterfaces` present -> `v1`.
   - Otherwise any of `url`, `preferredTransport`, `additionalInterfaces`,
     `protocolVersion`, `supportsExtendedAgentCard` present at the top
     level -> `v0.x`.
   - Otherwise -> `undetermined`.

2. **The v1 signal wins when both are present.** A card carrying
   `supportedInterfaces` *and* a legacy `url` is classified v1 and is
   validated, and it will fail - correctly, because it claims v1 structure
   and violates it. The census found 58 such cards; they are genuine
   defects and this ADR deliberately keeps them failing. Suppressing them
   would trade one false FAIL for one false PASS.

3. C012 SKIPs for both `v0.x` and `undetermined`. A missing version
   declaration must never convert into a scored schema failure. The
   general principle, which outlives this particular check: **when the
   scanner cannot establish that a requirement applies to a target, the
   check is not applicable, not failed.** ADR-0005 already put the
   scanner's own crashes (ERROR) on the failing side so that our bugs
   cannot inflate a grade; this is the same instinct pointed the other
   way, so that our ignorance cannot deflate one.

4. The third bucket is renamed `unknown` -> `undetermined`. The value is a
   conclusion the scanner reached, not a property of the card, and the old
   name invited reading it as the latter. The rename also makes it
   impossible to silently compare pre-fix and post-fix records: any
   consumer of the census dataset that sees `unknown` is looking at data
   produced under the defective rule.

## Consequences

- `spec_generation` is reported and stored as one of `v1`, `v0.x`,
  `undetermined`.
- Grades change: on the census sample, 26 of 304 scannable targets improve
  and F drops from 28 to 10. No target gets worse, because the change only
  ever converts a FAIL into a SKIP.
- GRADING_VERSION stays "1". ADR-0011's trigger is a change to a *released*
  grade and no dataset has been published; this fix lands before the first
  release, which is the whole point of finding it now.
- Regression fixtures are added to tests/conftest.py for the three shapes
  the census proved exist in the wild: a version-silent card carrying
  `url`; a v1 card with `supportedInterfaces`; and a v1 card that also
  carries legacy `url`/`protocolVersion`, which must keep failing. Fixtures
  are built from real captured card shapes, not invented ones - the
  divergence between fixtures and reality is what caused this defect and
  the fix has to close that gap, not just the code path.
- The `unknown` label in research/census-2026-08-22/data/census.jsonl is
  left as-is. It is a historical record of what the scanner did on that
  date and must not be rewritten.
