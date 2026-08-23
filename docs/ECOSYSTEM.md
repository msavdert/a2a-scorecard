# A2A ecosystem report

Aggregate measurement only. No individual operator or target is named anywhere in this report - see ADR-0018. Per-target results remain available in the published dataset for anyone who wants to reproduce these figures or recompute them under a different operator cap.

Generated: 2026-08-23T03:14:22+00:00

## Provenance

- Run(s): run-20260823T025632Z
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
- `throttled`: 1/2023 (0.0%) of capped target records
- `budget_exceeded`: 1/2023 (0.0%) of capped target records
- `deadline_exceeded`: 0/2023 (0.0%) of capped target records
- `skipped_recent`: 0/2023 (0.0%) of capped target records
- `skipped_throttled_group`: 0/2023 (0.0%) of capped target records
- `excluded`: 0/2023 (0.0%) of capped target records
- `ok`: 2021/2023 (99.9%) of capped target records

## Reachability and scannability

- Reachable (C001 concluded PASS or WARN - the endpoint answered at all, over HTTPS or plain HTTP): 1936/2021 (95.8%) of capped scanned targets
- Scannable (C011 concluded PASS - a parseable Agent Card was served): 1581/2021 (78.2%) of capped scanned targets

## Spec generation

- `undetermined`: 503/2021 (24.9%) of capped scanned targets
- `v0.x`: 1077/2021 (53.3%) of capped scanned targets
- `v1`: 441/2021 (21.8%) of capped scanned targets

## Grade distribution (stratified by spec generation, never pooled)

ADR-0017 rule 4: grades are never pooled across spec generations, because v0.x cards are measured against a smaller rubric (they skip C012, the heaviest single check) and score better on average for that reason alone, not because they are more conformant. `NG` ("not graded") means the scan did not measure enough to grade - it is not a failing grade and is never counted as one.

### `undetermined`

- A: 0/503 (0.0%) of capped undetermined scans
- B: 0/503 (0.0%) of capped undetermined scans
- C: 0/503 (0.0%) of capped undetermined scans
- D: 38/503 (7.6%) of capped undetermined scans
- F: 465/503 (92.4%) of capped undetermined scans
- NG: 0/503 (0.0%) of capped undetermined scans

### `v0.x`

- A: 0/1077 (0.0%) of capped v0.x scans
- B: 141/1077 (13.1%) of capped v0.x scans
- C: 0/1077 (0.0%) of capped v0.x scans
- D: 854/1077 (79.3%) of capped v0.x scans
- F: 1/1077 (0.1%) of capped v0.x scans
- NG: 81/1077 (7.5%) of capped v0.x scans

### `v1`

- A: 17/441 (3.9%) of capped v1 scans
- B: 53/441 (12.0%) of capped v1 scans
- C: 105/441 (23.8%) of capped v1 scans
- D: 114/441 (25.9%) of capped v1 scans
- F: 7/441 (1.6%) of capped v1 scans
- NG: 145/441 (32.9%) of capped v1 scans

## Agent Card location

- Well-known path (`/.well-known/agent-card.json`): 1357/1605 (84.5%) of capped targets with a card present
- Legacy path (`/.well-known/agent.json`): 248/1605 (15.5%) of capped targets with a card present

## Auth-gated endpoints

- 119/2021 (5.9%) of capped scanned targets. These returned 401/403 on the conformance probe and were, per policy, not probed further behind the gate.

## Posture and conditional-binding pass rates

Each rate is over the subset of scans where the check applied (non-SKIP); most cards do not declare every optional feature.

- TLS posture (C032) PASS rate: 1925/2015 (95.5%) of capped scans where C032 was applicable (non-SKIP)
- Card signature (C031) PASS rate: 25/466 (5.4%) of capped scans where C031 was applicable (non-SKIP)
- Streaming binding (C022) PASS rate: 5/1531 (0.3%) of capped scans where C022 was applicable (non-SKIP)
- REST/HTTP+JSON binding (C023) PASS rate: 9/648 (1.4%) of capped scans where C023 was applicable (non-SKIP)

## Probe coverage distribution

- n = 2021; median coverage = 0.69; Q1 = 0.69; Q3 = 0.88
- Coverage is applicable_weight / max_weight (ADR-0015): the fraction of the rubric a scan actually measured. Conditional checks (signature, security schemes, streaming, REST) SKIP on most targets by design, so coverage well below 1.0 is normal.

## Per-check status distribution

### C001 - Endpoint reachable over HTTPS

- `fail`: 85/2021 (4.2%) of capped scanned targets
- `pass`: 1935/2021 (95.7%) of capped scanned targets
- `warn`: 1/2021 (0.0%) of capped scanned targets

### C010 - Agent Card served at well-known URI

- `blocked`: 85/2021 (4.2%) of capped scanned targets
- `fail`: 331/2021 (16.4%) of capped scanned targets
- `pass`: 1357/2021 (67.1%) of capped scanned targets
- `warn`: 248/2021 (12.3%) of capped scanned targets

### C011 - Agent Card is valid JSON

- `blocked`: 416/2021 (20.6%) of capped scanned targets
- `fail`: 24/2021 (1.2%) of capped scanned targets
- `pass`: 1581/2021 (78.2%) of capped scanned targets

### C012 - Agent Card validates against official v1 schema

- `blocked`: 440/2021 (21.8%) of capped scanned targets
- `fail`: 365/2021 (18.1%) of capped scanned targets
- `pass`: 76/2021 (3.8%) of capped scanned targets
- `skip`: 1140/2021 (56.4%) of capped scanned targets

### C013 - Agent Card declares usable identity and interface

- `blocked`: 440/2021 (21.8%) of capped scanned targets
- `fail`: 72/2021 (3.6%) of capped scanned targets
- `pass`: 1346/2021 (66.6%) of capped scanned targets
- `warn`: 163/2021 (8.1%) of capped scanned targets

### C020 - Agent answers a spec-conformant SendMessage

- `blocked`: 512/2021 (25.3%) of capped scanned targets
- `fail`: 989/2021 (48.9%) of capped scanned targets
- `pass`: 196/2021 (9.7%) of capped scanned targets
- `skip`: 173/2021 (8.6%) of capped scanned targets
- `warn`: 151/2021 (7.5%) of capped scanned targets

### C021 - Unknown method rejected with JSON-RPC -32601

- `blocked`: 1501/2021 (74.3%) of capped scanned targets
- `fail`: 4/2021 (0.2%) of capped scanned targets
- `pass`: 217/2021 (10.7%) of capped scanned targets
- `skip`: 292/2021 (14.4%) of capped scanned targets
- `warn`: 7/2021 (0.3%) of capped scanned targets

### C022 - Declared streaming support answers a SendStreamingMessage

- `blocked`: 1501/2021 (74.3%) of capped scanned targets
- `fail`: 1/2021 (0.0%) of capped scanned targets
- `pass`: 5/2021 (0.2%) of capped scanned targets
- `skip`: 490/2021 (24.2%) of capped scanned targets
- `warn`: 24/2021 (1.2%) of capped scanned targets

### C023 - Declared HTTP+JSON binding answers a message:send

- `blocked`: 512/2021 (25.3%) of capped scanned targets
- `fail`: 118/2021 (5.8%) of capped scanned targets
- `pass`: 9/2021 (0.4%) of capped scanned targets
- `skip`: 1373/2021 (67.9%) of capped scanned targets
- `warn`: 9/2021 (0.4%) of capped scanned targets

### C030 - Declared security schemes are coherent

- `blocked`: 440/2021 (21.8%) of capped scanned targets
- `fail`: 5/2021 (0.2%) of capped scanned targets
- `pass`: 49/2021 (2.4%) of capped scanned targets
- `skip`: 1441/2021 (71.3%) of capped scanned targets
- `warn`: 86/2021 (4.3%) of capped scanned targets

### C031 - Agent Card signatures are structurally valid JWS

- `blocked`: 440/2021 (21.8%) of capped scanned targets
- `fail`: 1/2021 (0.0%) of capped scanned targets
- `pass`: 25/2021 (1.2%) of capped scanned targets
- `skip`: 1555/2021 (76.9%) of capped scanned targets

### C032 - TLS configuration and certificate posture

- `blocked`: 85/2021 (4.2%) of capped scanned targets
- `pass`: 1925/2021 (95.2%) of capped scanned targets
- `skip`: 6/2021 (0.3%) of capped scanned targets
- `warn`: 5/2021 (0.2%) of capped scanned targets

## Limitations

- **Selection bias runs upward.** Most candidate targets come from directories that health-check their own listings before publishing them, so this population skews toward endpoints that were already known to answer. Nothing here corrects for that.
- **This is the indie long tail, not enterprise deployments.** Publicly discoverable A2A endpoints skew toward solo builders, brokers, and single-page deployments. Enterprise adopters typically sit behind authentication and inside private networks, which a public scanner structurally cannot see (ADR-0018).
- Figures describe the capped, scannable-where-stated subset, not the A2A ecosystem as a whole. Every figure above states its own denominator for exactly this reason.

