# ADR-0002: Private-first development, Apache-2.0 from day one

Date: 2026-08-21. Status: accepted.

## Context

Options: develop in public from the first commit, or develop privately and
open the repository at a quality gate.

## Decision

Develop in a private repository until the ROADMAP v0.4 gate, then open
under Apache-2.0. The LICENSE file is committed from day one so the intent
is recorded and every contribution is made under known terms.

Reasons:

1. The project is a neutral-referee reputation play. A half-built scanner
   that mislabels working agents as non-compliant would burn credibility at
   first contact, and first impressions of a scorecard are not repeatable.
2. The scanning policy, opt-out process, and a manually reviewed first
   dataset must exist before third-party endpoints are publicly graded.
3. Apache-2.0 matches the A2A ecosystem (the spec and SDKs are Apache-2.0),
   which removes friction for vendoring spec files and for future
   contributors.

## Consequences

- CLAUDE.md rule 10: visibility change only on the owner's explicit
  instruction.
- No public issue tracker until launch; decisions land in ADRs instead.
