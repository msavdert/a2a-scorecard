# ADR-0023: State the real message-ping bound

Date: 2026-08-22. Status: accepted.
Amends docs/SCANNING-POLICY.md.

## Context

The policy says a scan sends "at most two message pings in total" and that
"at most one of the message pings may be a streaming request". Building
the policy-conformance test suite (ADR-0020) turned that prose into an
assertion for the first time, and the assertion fails.

Measured against the fake agent, a v1 card that declares streaming and
whose endpoint rejects the v1 `SendMessage` method sends **three**
message-bearing requests: the v1 `SendMessage` ping, the legacy
`message/send` retry that ADR-0005 permits to distinguish a dead endpoint
from spec drift, and then the streaming probe that ADR-0013 added. Plus
the error-handling probe, which the policy accounts for separately.

Nothing about that behaviour is accidental - each of the three is
individually authorised by an accepted ADR. What is wrong is the
arithmetic in the prose. The "at most two in total" sentence lives in the
REST bullet, where it was reasoning about REST versus JSON-RPC being
mutually exclusive; it was never updated when the streaming probe landed
in the same amendment cycle, and the "at most one of the message pings may
be a streaming request" sentence reads as though streaming is drawn from
the two rather than added to them.

This is not hypothetical. The 2026-08-22 census scanned 400 real
endpoints, and the spec-drift-plus-streaming shape occurs in that
population, so the scanner has already exceeded its own stated bound
against real targets. That is worth stating plainly rather than quietly
correcting.

## Decision

The policy is amended to state what the scanner actually does and what we
actually intend it to do:

- At most **two JSON-RPC SendMessage pings**: one v1 `SendMessage`, plus a
  single legacy `message/send` retry sent only when the v1 method is
  rejected with method-not-found.
- **Or** at most one REST `message:send` ping, only when the JSON-RPC
  pings are not applicable. JSON-RPC and REST remain mutually exclusive.
- **Plus** at most one streaming request, only to targets whose card
  declares streaming support.
- Therefore: **at most three message-bearing requests per scan**, plus the
  single error-handling probe, plus the read-only discovery GETs, all
  still inside the existing "fewer than ten requests" ceiling, which is
  unchanged and is now enforced by a counter in the transport rather than
  by review.

The alternative - suppressing the streaming probe whenever both JSON-RPC
pings were spent - was rejected. It would silently drop a capability check
precisely for spec-drifting agents, which are the population the check is
most informative about, and it would trade a real loss of measurement for
a difference of one benign request. The burden argument does not support
it: three benign pings and two benign pings are not materially different
to a target, and the ceiling that actually protects targets is the
ten-request budget, which is unchanged.

What is *not* relaxed: no new kind of request is authorised, no limit on
what a request may contain changes, and the ten-request budget stands.
This ADR narrows the gap between the prose and the code by correcting the
prose, having first confirmed that the code's behaviour is the behaviour
three accepted ADRs asked for.

## Consequences

- SCANNING-POLICY's "What a scan sends" and "Volume and pacing" sections
  are reworded to the accounting above.
- `tests/test_policy_conformance.py` asserts the real bound, decomposed:
  JSON-RPC pings <= 2, streaming plus REST <= 1, and their sum <= 3,
  across every fake-agent mode. The number in the policy is now a test,
  which is the only reason this discrepancy was findable at all.
- General lesson, recorded because it has now happened twice in one
  milestone: a limit written only in prose is a limit nobody is checking.
  ADR-0016's false FAILs and this bound were both found by turning a
  written claim into an executable one. Policy statements that can be
  tested should arrive with their test.
