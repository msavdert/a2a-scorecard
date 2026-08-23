# A2A ecosystem report

Aggregate measurement only. No individual operator or target is named anywhere in this report - see ADR-0018. Per-target results remain available in the published dataset for anyone who wants to reproduce these figures or recompute them under a different operator cap.

Generated: 2026-08-23T03:16:29+00:00

## Provenance

- Run(s): run-20260823T025632Z, run-20260823T031623Z
- Scanner version(s): 0.3.0
- Grading version(s): 1
- Spec version(s): v1.0.1
- Grading manifest digest(s): sha256:f92d433a0b3f9021e5f4ccf20e1b3d40f08f79a85f4de5edceb3c5b7b1a3e2e5

## Population and the operator cap

- Dataset holds 2479 target record(s) (raw n, uncapped).
- This report is computed over at most 2 record(s) per operator: 2023 target record(s) (capped n) across 1756 operator(s).
- The cap exists because the raw dataset has a long operator tail (a handful of operators run dozens to over a hundred subdomains each); without it, the figures below would describe those operators rather than the ecosystem. See ADR-0022.

## Outcomes (capped dataset)

Every capped target record, including absences. Absences (excluded, throttled, skipped, errored, budget/deadline-exceeded) are not scan results and are never counted as failures below.

- `error`: 0/2023 (0.0%) of capped target records
- `throttled`: 0/2023 (0.0%) of capped target records
- `budget_exceeded`: 0/2023 (0.0%) of capped target records
- `deadline_exceeded`: 0/2023 (0.0%) of capped target records
- `skipped_recent`: 2023/2023 (100.0%) of capped target records
- `skipped_throttled_group`: 0/2023 (0.0%) of capped target records
- `excluded`: 0/2023 (0.0%) of capped target records
- `ok`: 0/2023 (0.0%) of capped target records

## Reachability and scannability

- Reachable (C001 concluded PASS or WARN - the endpoint answered at all, over HTTPS or plain HTTP): 0/0 (n/a) of capped scanned targets
- Scannable (C011 concluded PASS - a parseable Agent Card was served): 0/0 (n/a) of capped scanned targets

## Spec generation


## Grade distribution (stratified by spec generation, never pooled)

ADR-0017 rule 4: grades are never pooled across spec generations, because v0.x cards are measured against a smaller rubric (they skip C012, the heaviest single check) and score better on average for that reason alone, not because they are more conformant. `NG` ("not graded") means the scan did not measure enough to grade - it is not a failing grade and is never counted as one.

## Agent Card location

- Well-known path (`/.well-known/agent-card.json`): 0/0 (n/a) of capped targets with a card present
- Legacy path (`/.well-known/agent.json`): 0/0 (n/a) of capped targets with a card present

## Auth-gated endpoints

- 0/0 (n/a) of capped scanned targets. These returned 401/403 on the conformance probe and were, per policy, not probed further behind the gate.

## Posture and conditional-binding pass rates

Each rate is over the subset of scans where the check applied (non-SKIP); most cards do not declare every optional feature.

- TLS posture (C032) PASS rate: 0/0 (n/a) of capped scans where C032 was applicable (non-SKIP)
- Card signature (C031) PASS rate: 0/0 (n/a) of capped scans where C031 was applicable (non-SKIP)
- Streaming binding (C022) PASS rate: 0/0 (n/a) of capped scans where C022 was applicable (non-SKIP)
- REST/HTTP+JSON binding (C023) PASS rate: 0/0 (n/a) of capped scans where C023 was applicable (non-SKIP)

## Probe coverage distribution

- n = 0; median coverage = n/a; Q1 = n/a; Q3 = n/a
- Coverage is applicable_weight / max_weight (ADR-0015): the fraction of the rubric a scan actually measured. Conditional checks (signature, security schemes, streaming, REST) SKIP on most targets by design, so coverage well below 1.0 is normal.

## Per-check status distribution

## Limitations

- **Selection bias runs upward.** Most candidate targets come from directories that health-check their own listings before publishing them, so this population skews toward endpoints that were already known to answer. Nothing here corrects for that.
- **This is the indie long tail, not enterprise deployments.** Publicly discoverable A2A endpoints skew toward solo builders, brokers, and single-page deployments. Enterprise adopters typically sit behind authentication and inside private networks, which a public scanner structurally cannot see (ADR-0018).
- Figures describe the capped, scannable-where-stated subset, not the A2A ecosystem as a whole. Every figure above states its own denominator for exactly this reason.

