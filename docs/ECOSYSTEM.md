# A2A ecosystem report

Aggregate measurement only. No individual operator or target is named anywhere in this report - see ADR-0018. Per-target results remain available in the published dataset for anyone who wants to reproduce these figures or recompute them under a different operator cap.

Generated: 2026-10-01T10:23:06+00:00

## Provenance

- Run(s): run-20260823T025632Z, run-20260901T083650Z, run-20261001T100518Z
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
- `throttled`: 3/2023 (0.1%) of capped target records
- `budget_exceeded`: 1/2023 (0.0%) of capped target records
- `deadline_exceeded`: 0/2023 (0.0%) of capped target records
- `skipped_recent`: 0/2023 (0.0%) of capped target records
- `skipped_throttled_group`: 2/2023 (0.1%) of capped target records
- `excluded`: 0/2023 (0.0%) of capped target records
- `ok`: 2017/2023 (99.7%) of capped target records

## Reachability and scannability

- Reachable (C001 concluded PASS or WARN - the endpoint answered at all, over HTTPS or plain HTTP): 1903/2017 (94.3%) of capped scanned targets
- Scannable (C011 concluded PASS - a parseable Agent Card was served): 1515/2017 (75.1%) of capped scanned targets

## Spec generation

- `undetermined`: 558/2017 (27.7%) of capped scanned targets
- `v0.x`: 1002/2017 (49.7%) of capped scanned targets
- `v1`: 457/2017 (22.7%) of capped scanned targets

## Grade distribution (stratified by spec generation, never pooled)

ADR-0017 rule 4: grades are never pooled across spec generations, because v0.x cards are measured against a smaller rubric (they skip C012, the heaviest single check) and score better on average for that reason alone, not because they are more conformant. `NG` ("not graded") means the scan did not measure enough to grade - it is not a failing grade and is never counted as one.

### `undetermined`

- A: 0/558 (0.0%) of capped undetermined scans
- B: 0/558 (0.0%) of capped undetermined scans
- C: 0/558 (0.0%) of capped undetermined scans
- D: 33/558 (5.9%) of capped undetermined scans
- F: 525/558 (94.1%) of capped undetermined scans
- NG: 0/558 (0.0%) of capped undetermined scans

### `v0.x`

- A: 0/1002 (0.0%) of capped v0.x scans
- B: 129/1002 (12.9%) of capped v0.x scans
- C: 0/1002 (0.0%) of capped v0.x scans
- D: 790/1002 (78.8%) of capped v0.x scans
- F: 0/1002 (0.0%) of capped v0.x scans
- NG: 83/1002 (8.3%) of capped v0.x scans

### `v1`

- A: 34/457 (7.4%) of capped v1 scans
- B: 57/457 (12.5%) of capped v1 scans
- C: 118/457 (25.8%) of capped v1 scans
- D: 117/457 (25.6%) of capped v1 scans
- F: 5/457 (1.1%) of capped v1 scans
- NG: 126/457 (27.6%) of capped v1 scans

## Agent Card location

- Well-known path (`/.well-known/agent-card.json`): 1323/1541 (85.9%) of capped targets with a card present
- Legacy path (`/.well-known/agent.json`): 218/1541 (14.1%) of capped targets with a card present

## Auth-gated endpoints

- 128/2017 (6.3%) of capped scanned targets. These returned 401/403 on the conformance probe and were, per policy, not probed further behind the gate.

## Posture and conditional-binding pass rates

Each rate is over the subset of scans where the check applied (non-SKIP); most cards do not declare every optional feature.

- TLS posture (C032) PASS rate: 1886/2011 (93.8%) of capped scans where C032 was applicable (non-SKIP)
- Card signature (C031) PASS rate: 54/557 (9.7%) of capped scans where C031 was applicable (non-SKIP)
- Streaming binding (C022) PASS rate: 4/1522 (0.3%) of capped scans where C022 was applicable (non-SKIP)
- REST/HTTP+JSON binding (C023) PASS rate: 8/695 (1.2%) of capped scans where C023 was applicable (non-SKIP)

## Probe coverage distribution

- n = 2017; median coverage = 0.69; Q1 = 0.69; Q3 = 0.94
- Coverage is applicable_weight / max_weight (ADR-0015): the fraction of the rubric a scan actually measured. Conditional checks (signature, security schemes, streaming, REST) SKIP on most targets by design, so coverage well below 1.0 is normal.

## Per-check status distribution

### C001 - Endpoint reachable over HTTPS

- `fail`: 114/2017 (5.7%) of capped scanned targets
- `pass`: 1902/2017 (94.3%) of capped scanned targets
- `warn`: 1/2017 (0.0%) of capped scanned targets

### C010 - Agent Card served at well-known URI

- `blocked`: 114/2017 (5.7%) of capped scanned targets
- `fail`: 362/2017 (17.9%) of capped scanned targets
- `pass`: 1323/2017 (65.6%) of capped scanned targets
- `warn`: 218/2017 (10.8%) of capped scanned targets

### C011 - Agent Card is valid JSON

- `blocked`: 476/2017 (23.6%) of capped scanned targets
- `fail`: 26/2017 (1.3%) of capped scanned targets
- `pass`: 1515/2017 (75.1%) of capped scanned targets

### C012 - Agent Card validates against official v1 schema

- `blocked`: 502/2017 (24.9%) of capped scanned targets
- `fail`: 367/2017 (18.2%) of capped scanned targets
- `pass`: 90/2017 (4.5%) of capped scanned targets
- `skip`: 1058/2017 (52.5%) of capped scanned targets

### C013 - Agent Card declares usable identity and interface

- `blocked`: 502/2017 (24.9%) of capped scanned targets
- `fail`: 64/2017 (3.2%) of capped scanned targets
- `pass`: 1299/2017 (64.4%) of capped scanned targets
- `warn`: 152/2017 (7.5%) of capped scanned targets

### C020 - Agent answers a spec-conformant SendMessage

- `blocked`: 566/2017 (28.1%) of capped scanned targets
- `fail`: 928/2017 (46.0%) of capped scanned targets
- `pass`: 199/2017 (9.9%) of capped scanned targets
- `skip`: 161/2017 (8.0%) of capped scanned targets
- `warn`: 163/2017 (8.1%) of capped scanned targets

### C021 - Unknown method rejected with JSON-RPC -32601

- `blocked`: 1494/2017 (74.1%) of capped scanned targets
- `fail`: 5/2017 (0.2%) of capped scanned targets
- `pass`: 217/2017 (10.8%) of capped scanned targets
- `skip`: 289/2017 (14.3%) of capped scanned targets
- `warn`: 12/2017 (0.6%) of capped scanned targets

### C022 - Declared streaming support answers a SendStreamingMessage

- `blocked`: 1494/2017 (74.1%) of capped scanned targets
- `fail`: 1/2017 (0.0%) of capped scanned targets
- `pass`: 4/2017 (0.2%) of capped scanned targets
- `skip`: 495/2017 (24.5%) of capped scanned targets
- `warn`: 23/2017 (1.1%) of capped scanned targets

### C023 - Declared HTTP+JSON binding answers a message:send

- `blocked`: 566/2017 (28.1%) of capped scanned targets
- `fail`: 111/2017 (5.5%) of capped scanned targets
- `pass`: 8/2017 (0.4%) of capped scanned targets
- `skip`: 1322/2017 (65.5%) of capped scanned targets
- `warn`: 10/2017 (0.5%) of capped scanned targets

### C030 - Declared security schemes are coherent

- `blocked`: 502/2017 (24.9%) of capped scanned targets
- `fail`: 4/2017 (0.2%) of capped scanned targets
- `pass`: 59/2017 (2.9%) of capped scanned targets
- `skip`: 1358/2017 (67.3%) of capped scanned targets
- `warn`: 94/2017 (4.7%) of capped scanned targets

### C031 - Agent Card signatures are structurally valid JWS

- `blocked`: 502/2017 (24.9%) of capped scanned targets
- `fail`: 1/2017 (0.0%) of capped scanned targets
- `pass`: 54/2017 (2.7%) of capped scanned targets
- `skip`: 1460/2017 (72.4%) of capped scanned targets

### C032 - TLS configuration and certificate posture

- `blocked`: 114/2017 (5.7%) of capped scanned targets
- `pass`: 1886/2017 (93.5%) of capped scanned targets
- `skip`: 6/2017 (0.3%) of capped scanned targets
- `warn`: 11/2017 (0.5%) of capped scanned targets

## Limitations

- **Selection bias runs upward.** Most candidate targets come from directories that health-check their own listings before publishing them, so this population skews toward endpoints that were already known to answer. Nothing here corrects for that.
- **This is the indie long tail, not enterprise deployments.** Publicly discoverable A2A endpoints skew toward solo builders, brokers, and single-page deployments. Enterprise adopters typically sit behind authentication and inside private networks, which a public scanner structurally cannot see (ADR-0018).
- Figures describe the capped, scannable-where-stated subset, not the A2A ecosystem as a whole. Every figure above states its own denominator for exactly this reason.

