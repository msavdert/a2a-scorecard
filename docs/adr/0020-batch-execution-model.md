# ADR-0020: Batch execution model - pacing, throttling, budgets, and abort semantics

Date: 2026-08-22. Status: accepted.
Makes docs/SCANNING-POLICY.md's "Volume and pacing" section executable.

## Context

`cli.py` scans a list of URLs in a plain list comprehension: no per-host
serialisation, no pacing, no 429 handling, no enforced request budget.
The policy has required all four since v0.1; only the census harness ever
implemented them, and it lives in `research/`. An unattended monthly run
(ADR-0018) cannot depend on a research script, and a policy that only
holds when someone remembers to use the right script is not a policy.

## Decision

### Scheduling: operator groups, workers across them

Targets are grouped by operator unit; one worker owns a whole group and
walks it sequentially; a thread pool runs groups concurrently. Because a
host belongs to exactly one operator unit, serialising per group implies
serialising per host, which is what the policy requires - and it also
covers the raw-socket TLS handshake, which never passes through httpx.

Groups are scheduled longest-first so a large operator does not become
the tail, and members are ordered by normalised URL so a resumed run
replays deterministically.

Concurrency default 8, clamped to [1, 16]. Empirically grounded: the
census ran 400 targets at 8 workers and observed zero 429 responses.
Raising it buys nothing measurable and increases simultaneous load on
shared PaaS infrastructure, where many distinct hostnames sit behind one
provider.

### A per-host pacer keyed on the real request host

Group scheduling is not sufficient on its own. A card's declared endpoint
can point at a host the scheduler never grouped, so the pacer keys on the
host of the request actually being issued, not on the target URL. 0.5s
between consecutive requests to the same host; 3.0s between targets
within an operator group.

Worth recording, because it corrects a belief the census harness invites:
the within-operator pause was nearly inert in the census - 400 targets
fell into 396 groups, so almost every group was a singleton and the pause
fired about four times all run. The politeness came from the worker cap
alone. Per-host pacing fires on every request and is the knob that
actually does the work.

### 429 handling belongs in the transport, and never retries a POST

There is no shared request helper in this codebase: each check calls the
client directly and interprets the status itself. So the batch layer
cannot see a 429 (it never sees a response), and pushing the logic into
the checks would mean editing five call sites and changing check
semantics - today a 429 on the well-known path makes C010 FAIL "no card",
which is an ADR-level change to five checks. Therefore 429 handling goes
in a custom `httpx.BaseTransport` beneath the client: one place, no check
edits, and it also covers the streaming request.

- **GET**: parse `Retry-After` (delta-seconds or HTTP-date; unparseable
  defaults to 5s). If it exceeds a 60s cap, do not sleep - abort. Else
  sleep and retry once. A second 429 aborts.
- **Any non-GET: never retried.** This is the load-bearing rule. Retrying
  a POST would spend a second `SendMessage` ping, and the policy bounds a
  scan to at most two message pings total. A retry policy that quietly
  doubles the pings is a policy violation implemented as a feature.

A throttled scan aborts and is recorded as `throttled` with no report and
no grade. That is stricter than the policy demands and it is a
dataset-quality decision as much as a courtesy: a 429-induced F written
into an append-only permanent corpus is a lie about the target that we
would carry forever. When a target throttles, its whole operator group is
quarantined for the run - a host that said stop should not receive three
more scans from us in the next ten seconds.

### Enforced budgets, not hoped-for ones

- 9 requests per scan, enforced by a counter in the transport, making the
  policy's "fewer than 10" true by construction rather than by review.
  The TLS handshake is counted separately and is capped at one by there
  being one check that performs one.
- `max_redirects=3`. `scan.py` follows redirects and each hop spends
  budget; httpx's default of 20 exceeds the whole budget.
- 90s per-scan wall-clock deadline, checked between requests. The census
  worst case was 10s, so this is runaway protection only.
- A global circuit breaker: 25 consecutive errors aborts the run.
  Twenty-five consecutive failures unattended means our egress is broken,
  not that the ecosystem died, and recording hundreds of fabricated
  failures into a permanent corpus is worse than stopping.

### Two implementation facts that are easy to get wrong

Both are recorded here because both would silently defeat the design and
neither is visible from the call site:

1. `ScanAborted` and its subclasses must **not** derive from
   `httpx.HTTPError`, or the checks' own exception handlers will catch an
   abort and emit a FAIL.
2. `scan.py`'s blanket `except Exception` - which exists so a crashing
   check cannot kill a scan - must re-raise `ScanAborted` first, or every
   abort becomes a scored ERROR.

### Outcome taxonomy

Recorded verbatim per target: `ok`, `error`, `throttled`,
`budget_exceeded`, `deadline_exceeded`, `skipped_recent`,
`skipped_throttled_group`, `excluded`. Only `ok` carries a report and a
grade; the rest are absences and must never be aggregated as failures.

### Re-scan floor

At most one scan per target per day, enforced from the run index. The
library API accepts an interval so tests can pass zero; **the CLI exposes
no flag to lower it.** Policy floors are not command-line arguments.

## Testing

Everything runs against the in-process fake agent (CLAUDE.md rule 2). The
fake agent grows a request journal of `(start, end, method, path,
user_agent)` tuples, throttling modes, a `threading.Barrier` mode, and a
mode whose card points at a second fixture server.

The journal is what makes these assertions deterministic rather than
timing-flaky: per-host serialisation is "no two intervals on the same
netloc overlap", and cross-host parallelism is a barrier that times out
if the runner serialised everything - so both directions fail loudly
instead of passing by luck. Pacing arithmetic is tested with an injected
clock and a recording sleep, in zero wall-clock time.

A new `tests/test_policy_conformance.py` asserts each policy line
directly - request count per scan, at most two message pings across every
fake-agent mode including the throttle modes, the User-Agent on every
request, and an excluded target producing an empty journal. Policy
conformance becomes a regression test rather than a review item.

## Consequences

- New `transport.py` and `batch.py`; `scan.py` gains the `ScanAborted`
  re-raise and an optional injected transport; `ProbeContext` carries the
  pacer; the TLS check takes a pacer slot.
- `scan.py` changes, so CLAUDE.md's review tiers require a tier-2
  reviewer pass on this work.
- Resumability and the dataset records these outcomes land in ADR-0021.
