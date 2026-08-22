# ADR-0001: Project goal and name

Date: 2026-08-21. Status: accepted.

## Context

Research (2026-08-21, see the a2a directory's research notes) showed a
documented gap between advertised and actual A2A protocol support:
a2aproject/A2A#1755 found 0 of 50 agents advertising A2A actually answered
a conformant request. No neutral conformance-measurement service exists;
the official `a2a-tck` targets implementers testing themselves, not
third-party measurement of live endpoints.

## Decision

Build an independent conformance scanner plus a public scorecard for live
A2A endpoints - the SSL Labs model applied to agent interoperability.
Name: `a2a-scorecard` (zero GitHub name collisions at creation time;
descriptive; does not imply official status - reinforced by a README
disclaimer). The public-facing brand can be renamed before launch; the
package name stays.

## Consequences

The project's value is credibility. Correctness of a FAIL verdict matters
more than feature count; a wrongly failed vendor is reputational damage.
Hence the strict probe policy, permanent check IDs, and the manual review
gate before public launch (ROADMAP v0.4).
