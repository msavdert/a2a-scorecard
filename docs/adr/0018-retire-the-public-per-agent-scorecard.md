# ADR-0018: Retire the public per-agent scorecard; the product is the dataset and the aggregate report

Date: 2026-08-22. Status: accepted.
Supersedes the v0.4 and v0.5 milestones as written in ROADMAP.md.
Amends docs/SCANNING-POLICY.md (see Consequences).

## Context

ADR-0001 set the goal as a public scorecard, "SSL Labs for A2A". The
v0.4 gate turned that into concrete obligations: a browsable site of
per-agent letter grades, a badge programme in v0.5, and - self-imposed -
pre-notification of every listed endpoint owner with a correction window
of at least 14 days before any grade goes public.

The 2026-08-22 census (docs/CENSUS-2026-08-22.md) measured the
population those obligations would apply to and, in doing so, made their
cost calculable for the first time. Three findings decide this ADR.

**The obligations do not automate, and they scale with success.** The
machine half of this project automates essentially completely: scanning
1,400 endpoints costs about 27 minutes of serial compute (measured
median 0.67s per target over 400 scans), and sampling, scoring, dataset
append and report generation are all deterministic code. The human half
does not automate at all. Finding contact addresses for ~1,400 endpoints
that are mostly solo builders and single-page PaaS deployments is
manual and frequently impossible; processing replies, reviewing for
false FAILs before publication (a v0.4 gate requirement), handling
disputes over named grades, and defending the methodology are all
owner-time, permanently, and every additional endpoint adds more of it.
A project whose running cost rises with its reach is not a project that
can be left running.

**The population that can be scored has no budget, and the population
with a budget cannot be scored.** The census found the public A2A
population to be the indie long tail: x402 brokers, signal vendors,
solo builders. The enterprise adopters behind the Linux Foundation's
150+ organisations figure are auth-gated and inside private networks.
That is not a gap to be closed by better tooling; a public scanner is
structurally unable to see them. So the audience a per-agent scorecard
would serve is disjoint from the audience that could ever fund it.

**The comparables are not lone-operator businesses.** SSL Labs is a
free loss leader attached to Qualys' enterprise sales funnel. OpenSSF
Scorecard is foundation-funded and foundation-adjacent. Both carry the
correspondence load of public per-subject grading on an institution.
This project has neither a funnel nor a foundation, and CLAUDE.md rule 9
forbids implying the foundation affiliation that would supply one.

What the census also showed is that the measurement itself is valuable
and nobody else is making it. The incumbent directory's "grade" is
`uptime_30d` plus p95 latency; it exposes no TLS field, no schema
validation result and no signature field. Schema and protocol
conformance, TLS posture and card signatures are unmeasured by anyone
in this ecosystem. That gap is real, and reaching it does not require
publishing a letter grade next to a named company.

## Decision

The public per-agent scorecard is retired before it is built. The
project's output is three things:

1. **The scanner**, as a public CLI and library. Anyone can grade their
   own endpoint, or anyone else's, on demand and locally. This is where
   the per-agent grading capability lives from now on.
2. **An append-only longitudinal dataset** of scan results, per ADR-0011,
   with every record stamped with scanner, grading-methodology and spec
   version. This remains the primary long-term product.
3. **A periodically regenerated aggregate ecosystem report** built from
   the dataset. Aggregate means it characterises the population and
   names no individual operator.

Specifically retired:

- The scorecard site of browsable, comparable, per-agent letter grades.
- The v0.5 badge programme.
- The v0.4 pre-notification programme. It existed to make per-agent
  publication defensible; with no per-agent publication there is nothing
  to notify about, and a 1,400-endpoint notification round is the single
  largest cost item in the retired plan.
- Scheduled re-scanning framed as keeping a public scorecard current.
  Scheduled re-scanning as dataset accumulation is retained and is the
  automation this project is being brought to.

Explicitly NOT retired, and worth being precise about because it is the
uncomfortable part of this decision: the dataset contains per-target
rows with target URLs and letter grades, and the dataset is published.
This ADR does not pretend otherwise. The claim is not that per-target
results become secret; it is that there is a real difference in kind
between a data file that a researcher can reproduce our aggregates from
and a ranked, browsable site that invites the public to look up and
compare named agents. The first is measurement of publicly advertised
endpoints, which is ordinary and which Censys, Shodan and OpenSSF
Scorecard all do at far greater scale. The second is a product with an
audience, and the audience is what generates the correspondence load.
We are declining to build the second.

Pseudonymising the target field was considered and rejected as theatre:
the target list is published for reproducibility, so hashed targets
would be re-linkable in one pass, and the hashing would buy nothing but
the appearance of care.

## Rationale

The owner's constraint is that this project must survive without
consuming his time, and must not consume time in exchange for nothing.
The retired plan failed both halves: it had unbounded human cost and no
revenue path. What is kept is the part that is cheap to run, is not
being done by anyone else, and preserves the option value - if A2A
grows an audience that would fund per-agent grading, the dataset will
by then hold years of history and the scanner will already exist. The
decision is reversible in the only direction that matters; building the
scorecard first and discovering the correspondence load afterwards is
not.

Rejecting the alternative of abandoning the project entirely: the
scanner is complete and correct once the defects in this milestone are
fixed, the census is already a result nobody else holds, and the
marginal cost of keeping a monthly cron alive is approximately zero.
Killing it would discard an asset to save a cost that does not exist.

## Consequences

- ROADMAP.md is rewritten: v0.4 and v0.5 as specified are removed, and
  replaced by a milestone that delivers the automated run loop and the
  aggregate report. The public launch gate becomes a gate on publishing
  the repository and the first report, not on grading named agents.
- docs/SCANNING-POLICY.md is amended in two places. The re-scan clause
  no longer refers to "the public scorecard"; the binding limit is now
  at most daily per target, with the automated run configured monthly.
  The opt-out clause is retained unchanged and strengthened in scope: it
  now covers exclusion from scanning altogether, not only from a
  scorecard, and remains honoured permanently via a committed exclusion
  list. Everything else in the policy is unchanged; nothing here relaxes
  a limit on what a scan may send.
- README is rewritten for a public audience and must state plainly what
  is measured, that grades are reproducible from the published dataset,
  and how to request correction or exclusion.
- ADR-0001's framing survives as the goal ("independent conformance
  measurement of A2A endpoints") but its "SSL Labs for A2A" phrasing is
  no longer accurate and is retired with this ADR. The census gives a
  sharper positioning against the actual gap: schema and protocol
  conformance, TLS posture and card signatures, none of which any
  public A2A directory currently measures.
- ADR-0011 is unaffected and is in fact promoted: with the scorecard
  gone, the dataset is no longer the input to the product, it is the
  product.
- ADR-0015's deferred question - whether a letter grade should be gated
  on probe coverage - still needs answering, because the scanner still
  emits letter grades. It is answered in ADR-0017, not here.
