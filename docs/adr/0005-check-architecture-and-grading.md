# ADR-0005: Check architecture and grading semantics

Date: 2026-08-21. Status: accepted.

## Check architecture

- A check is one class in one module under `checks/`, with permanent
  ClassVar metadata: `check_id`, `title`, `stage`, `weight`, `requires`.
- Stages: 0 reachability, 1 Agent Card, 2 live protocol, 3 security
  (reserved for v0.2). `scan.py` runs checks ordered by (stage, check_id).
- `requires` lists check IDs that must have finished PASS or WARN; otherwise
  the dependent check is reported BLOCKED and never executed. Exception:
  a dependency that ended SKIP propagates SKIP, not BLOCKED - when a probe
  is not applicable, everything downstream of it is not applicable either
  and must not count against the score.
- Check IDs are numbered with gaps (C001, C010, C020...) so new checks can
  land inside a stage without renumbering. IDs are permanent public API.

## Statuses

- PASS: requirement met.
- WARN: met with a defect (legacy location, plain http, auth-gated, drift).
- FAIL: requirement not met.
- BLOCKED: dependency failed; the check could not run.
- SKIP: not applicable to this target (e.g. v1 schema check on a
  v0.x-generation card). The only status excluded from scoring.
- ERROR: the check itself crashed; treated like FAIL in scoring so scanner
  bugs never inflate a target's grade.

## Scoring

score = 100 * sum(weight * earned) / sum(weight) over non-SKIP results,
where earned is PASS 1.0, WARN 0.5, FAIL/BLOCKED/ERROR 0.0.
BLOCKED stays in the denominator deliberately: a target with no Agent Card
must not score better than one with a card that merely has defects.

Letter bands: >=90 A, >=75 B, >=60 C, >=40 D, else F.

## v0.1 weights

C001 reachability 10, C010 card present 20, C011 card parses 10,
C012 schema valid 20, C013 card semantics 15, C020 SendMessage ping 25,
C021 error handling 10.

## Known judgment calls

- Auth-gated endpoints (401/403 on ping) get WARN, not FAIL: requiring auth
  is spec-legal; what we cannot verify we do not certify either way.
- A v1-generation card whose endpoint only answers legacy v0.x methods gets
  WARN with "spec drift" evidence.
- v0.x-generation agents are graded against what applies to them (v1-only
  checks SKIP) and labeled with `spec_generation` in the report; the
  scorecard will display generation alongside grade.
- A card that legally declares only non-JSONRPC bindings (GRPC, HTTP+JSON)
  is never probed over JSON-RPC: C020/C021 SKIP so the missing binding
  neither helps nor hurts the grade. The REST binding probe arrives in
  v0.2; until then such agents are graded on card quality alone.
- The SendMessage probe is at most two POSTs, not one: when a v1 card's
  endpoint rejects the v1 `SendMessage` method with -32601, a single retry
  with the legacy `message/send` method distinguishes "dead endpoint" from
  "spec drift". The scanning policy states the same bound.

Changing any semantics above requires a superseding ADR plus test updates
in the same commit.
