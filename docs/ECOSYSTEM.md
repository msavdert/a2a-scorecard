# A2A ecosystem report

Aggregate measurement only. No individual operator or target is named anywhere in this report - see ADR-0018. Per-target results remain available in the published dataset for anyone who wants to reproduce these figures or recompute them under a different operator cap.

Generated: 2026-09-01T08:54:51+00:00

## Provenance

- Run(s): run-20260823T025632Z, run-20260901T083650Z
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

- Reachable (C001 concluded PASS or WARN - the endpoint answered at all, over HTTPS or plain HTTP): 1928/2021 (95.4%) of capped scanned targets
- Scannable (C011 concluded PASS - a parseable Agent Card was served): 1570/2021 (77.7%) of capped scanned targets

## Spec generation

- `undetermined`: 512/2021 (25.3%) of capped scanned targets
- `v0.x`: 1064/2021 (52.6%) of capped scanned targets
- `v1`: 445/2021 (22.0%) of capped scanned targets

## Grade distribution (stratified by spec generation, never pooled)

ADR-0017 rule 4: grades are never pooled across spec generations, because v0.x cards are measured against a smaller rubric (they skip C012, the heaviest single check) and score better on average for that reason alone, not because they are more conformant. `NG` ("not graded") means the scan did not measure enough to grade - it is not a failing grade and is never counted as one.

### `undetermined`

- A: 0/512 (0.0%) of capped undetermined scans
- B: 0/512 (0.0%) of capped undetermined scans
- C: 0/512 (0.0%) of capped undetermined scans
- D: 37/512 (7.2%) of capped undetermined scans
- F: 475/512 (92.8%) of capped undetermined scans
- NG: 0/512 (0.0%) of capped undetermined scans

### `v0.x`

- A: 0/1064 (0.0%) of capped v0.x scans
- B: 137/1064 (12.9%) of capped v0.x scans
- C: 0/1064 (0.0%) of capped v0.x scans
- D: 838/1064 (78.8%) of capped v0.x scans
- F: 1/1064 (0.1%) of capped v0.x scans
- NG: 88/1064 (8.3%) of capped v0.x scans

### `v1`

- A: 30/445 (6.7%) of capped v1 scans
- B: 45/445 (10.1%) of capped v1 scans
- C: 113/445 (25.4%) of capped v1 scans
- D: 117/445 (26.3%) of capped v1 scans
- F: 7/445 (1.6%) of capped v1 scans
- NG: 133/445 (29.9%) of capped v1 scans

## Agent Card location

- Well-known path (`/.well-known/agent-card.json`): 1356/1595 (85.0%) of capped targets with a card present
- Legacy path (`/.well-known/agent.json`): 239/1595 (15.0%) of capped targets with a card present

## Auth-gated endpoints

- 130/2021 (6.4%) of capped scanned targets. These returned 401/403 on the conformance probe and were, per policy, not probed further behind the gate.

## Posture and conditional-binding pass rates

Each rate is over the subset of scans where the check applied (non-SKIP); most cards do not declare every optional feature.

- TLS posture (C032) PASS rate: 1913/2015 (94.9%) of capped scans where C032 was applicable (non-SKIP)
- Card signature (C031) PASS rate: 39/491 (7.9%) of capped scans where C031 was applicable (non-SKIP)
- Streaming binding (C022) PASS rate: 4/1528 (0.3%) of capped scans where C022 was applicable (non-SKIP)
- REST/HTTP+JSON binding (C023) PASS rate: 6/649 (0.9%) of capped scans where C023 was applicable (non-SKIP)

## Probe coverage distribution

- n = 2021; median coverage = 0.69; Q1 = 0.69; Q3 = 0.88
- Coverage is applicable_weight / max_weight (ADR-0015): the fraction of the rubric a scan actually measured. Conditional checks (signature, security schemes, streaming, REST) SKIP on most targets by design, so coverage well below 1.0 is normal.

## Per-check status distribution

### C001 - Endpoint reachable over HTTPS

- `fail`: 93/2021 (4.6%) of capped scanned targets
- `pass`: 1927/2021 (95.3%) of capped scanned targets
- `warn`: 1/2021 (0.0%) of capped scanned targets

### C010 - Agent Card served at well-known URI

- `blocked`: 93/2021 (4.6%) of capped scanned targets
- `fail`: 333/2021 (16.5%) of capped scanned targets
- `pass`: 1356/2021 (67.1%) of capped scanned targets
- `warn`: 239/2021 (11.8%) of capped scanned targets

### C011 - Agent Card is valid JSON

- `blocked`: 426/2021 (21.1%) of capped scanned targets
- `fail`: 25/2021 (1.2%) of capped scanned targets
- `pass`: 1570/2021 (77.7%) of capped scanned targets

### C012 - Agent Card validates against official v1 schema

- `blocked`: 451/2021 (22.3%) of capped scanned targets
- `fail`: 351/2021 (17.4%) of capped scanned targets
- `pass`: 94/2021 (4.7%) of capped scanned targets
- `skip`: 1125/2021 (55.7%) of capped scanned targets

### C013 - Agent Card declares usable identity and interface

- `blocked`: 451/2021 (22.3%) of capped scanned targets
- `fail`: 70/2021 (3.5%) of capped scanned targets
- `pass`: 1337/2021 (66.2%) of capped scanned targets
- `warn`: 163/2021 (8.1%) of capped scanned targets

### C020 - Agent answers a spec-conformant SendMessage

- `blocked`: 521/2021 (25.8%) of capped scanned targets
- `fail`: 979/2021 (48.4%) of capped scanned targets
- `pass`: 192/2021 (9.5%) of capped scanned targets
- `skip`: 164/2021 (8.1%) of capped scanned targets
- `warn`: 165/2021 (8.2%) of capped scanned targets

### C021 - Unknown method rejected with JSON-RPC -32601

- `blocked`: 1500/2021 (74.2%) of capped scanned targets
- `fail`: 5/2021 (0.2%) of capped scanned targets
- `pass`: 213/2021 (10.5%) of capped scanned targets
- `skip`: 294/2021 (14.5%) of capped scanned targets
- `warn`: 9/2021 (0.4%) of capped scanned targets

### C022 - Declared streaming support answers a SendStreamingMessage

- `blocked`: 1500/2021 (74.2%) of capped scanned targets
- `fail`: 1/2021 (0.0%) of capped scanned targets
- `pass`: 4/2021 (0.2%) of capped scanned targets
- `skip`: 493/2021 (24.4%) of capped scanned targets
- `warn`: 23/2021 (1.1%) of capped scanned targets

### C023 - Declared HTTP+JSON binding answers a message:send

- `blocked`: 521/2021 (25.8%) of capped scanned targets
- `fail`: 112/2021 (5.5%) of capped scanned targets
- `pass`: 6/2021 (0.3%) of capped scanned targets
- `skip`: 1372/2021 (67.9%) of capped scanned targets
- `warn`: 10/2021 (0.5%) of capped scanned targets

### C030 - Declared security schemes are coherent

- `blocked`: 451/2021 (22.3%) of capped scanned targets
- `fail`: 5/2021 (0.2%) of capped scanned targets
- `pass`: 56/2021 (2.8%) of capped scanned targets
- `skip`: 1424/2021 (70.5%) of capped scanned targets
- `warn`: 85/2021 (4.2%) of capped scanned targets

### C031 - Agent Card signatures are structurally valid JWS

- `blocked`: 451/2021 (22.3%) of capped scanned targets
- `fail`: 1/2021 (0.0%) of capped scanned targets
- `pass`: 39/2021 (1.9%) of capped scanned targets
- `skip`: 1530/2021 (75.7%) of capped scanned targets

### C032 - TLS configuration and certificate posture

- `blocked`: 93/2021 (4.6%) of capped scanned targets
- `pass`: 1913/2021 (94.7%) of capped scanned targets
- `skip`: 6/2021 (0.3%) of capped scanned targets
- `warn`: 9/2021 (0.4%) of capped scanned targets

## Limitations

- **Selection bias runs upward.** Most candidate targets come from directories that health-check their own listings before publishing them, so this population skews toward endpoints that were already known to answer. Nothing here corrects for that.
- **This is the indie long tail, not enterprise deployments.** Publicly discoverable A2A endpoints skew toward solo builders, brokers, and single-page deployments. Enterprise adopters typically sit behind authentication and inside private networks, which a public scanner structurally cannot see (ADR-0018).
- Figures describe the capped, scannable-where-stated subset, not the A2A ecosystem as a whole. Every figure above states its own denominator for exactly this reason.

