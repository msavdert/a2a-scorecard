# A2A ecosystem report

Aggregate measurement only. No individual operator or target is named anywhere in this report - see ADR-0018. Per-target results remain available in the published dataset for anyone who wants to reproduce these figures or recompute them under a different operator cap.

Generated: 2026-11-01T10:41:12+00:00

## Provenance

- Run(s): run-20260823T025632Z, run-20260901T083650Z, run-20261001T100518Z, run-20261101T102428Z
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

- Reachable (C001 concluded PASS or WARN - the endpoint answered at all, over HTTPS or plain HTTP): 1879/2017 (93.2%) of capped scanned targets
- Scannable (C011 concluded PASS - a parseable Agent Card was served): 1455/2017 (72.1%) of capped scanned targets

## Spec generation

- `undetermined`: 619/2017 (30.7%) of capped scanned targets
- `v0.x`: 922/2017 (45.7%) of capped scanned targets
- `v1`: 476/2017 (23.6%) of capped scanned targets

## Grade distribution (stratified by spec generation, never pooled)

ADR-0017 rule 4: grades are never pooled across spec generations, because v0.x cards are measured against a smaller rubric (they skip C012, the heaviest single check) and score better on average for that reason alone, not because they are more conformant. `NG` ("not graded") means the scan did not measure enough to grade - it is not a failing grade and is never counted as one.

### `undetermined`

- A: 0/619 (0.0%) of capped undetermined scans
- B: 0/619 (0.0%) of capped undetermined scans
- C: 0/619 (0.0%) of capped undetermined scans
- D: 34/619 (5.5%) of capped undetermined scans
- F: 585/619 (94.5%) of capped undetermined scans
- NG: 0/619 (0.0%) of capped undetermined scans

### `v0.x`

- A: 0/922 (0.0%) of capped v0.x scans
- B: 118/922 (12.8%) of capped v0.x scans
- C: 0/922 (0.0%) of capped v0.x scans
- D: 725/922 (78.6%) of capped v0.x scans
- F: 0/922 (0.0%) of capped v0.x scans
- NG: 79/922 (8.6%) of capped v0.x scans

### `v1`

- A: 25/476 (5.3%) of capped v1 scans
- B: 72/476 (15.1%) of capped v1 scans
- C: 131/476 (27.5%) of capped v1 scans
- D: 113/476 (23.7%) of capped v1 scans
- F: 5/476 (1.1%) of capped v1 scans
- NG: 130/476 (27.3%) of capped v1 scans

## Agent Card location

- Well-known path (`/.well-known/agent-card.json`): 1282/1483 (86.4%) of capped targets with a card present
- Legacy path (`/.well-known/agent.json`): 201/1483 (13.6%) of capped targets with a card present

## Auth-gated endpoints

- 132/2017 (6.5%) of capped scanned targets. These returned 401/403 on the conformance probe and were, per policy, not probed further behind the gate.

## Posture and conditional-binding pass rates

Each rate is over the subset of scans where the check applied (non-SKIP); most cards do not declare every optional feature.

- TLS posture (C032) PASS rate: 1871/2011 (93.0%) of capped scans where C032 was applicable (non-SKIP)
- Card signature (C031) PASS rate: 57/620 (9.2%) of capped scans where C031 was applicable (non-SKIP)
- Streaming binding (C022) PASS rate: 7/1516 (0.5%) of capped scans where C022 was applicable (non-SKIP)
- REST/HTTP+JSON binding (C023) PASS rate: 8/759 (1.1%) of capped scans where C023 was applicable (non-SKIP)

## Probe coverage distribution

- n = 2017; median coverage = 0.69; Q1 = 0.69; Q3 = 1.00
- Coverage is applicable_weight / max_weight (ADR-0015): the fraction of the rubric a scan actually measured. Conditional checks (signature, security schemes, streaming, REST) SKIP on most targets by design, so coverage well below 1.0 is normal.

## Per-check status distribution

### C001 - Endpoint reachable over HTTPS

- `fail`: 138/2017 (6.8%) of capped scanned targets
- `pass`: 1878/2017 (93.1%) of capped scanned targets
- `warn`: 1/2017 (0.0%) of capped scanned targets

### C010 - Agent Card served at well-known URI

- `blocked`: 138/2017 (6.8%) of capped scanned targets
- `fail`: 396/2017 (19.6%) of capped scanned targets
- `pass`: 1282/2017 (63.6%) of capped scanned targets
- `warn`: 201/2017 (10.0%) of capped scanned targets

### C011 - Agent Card is valid JSON

- `blocked`: 534/2017 (26.5%) of capped scanned targets
- `fail`: 28/2017 (1.4%) of capped scanned targets
- `pass`: 1455/2017 (72.1%) of capped scanned targets

### C012 - Agent Card validates against official v1 schema

- `blocked`: 562/2017 (27.9%) of capped scanned targets
- `fail`: 389/2017 (19.3%) of capped scanned targets
- `pass`: 87/2017 (4.3%) of capped scanned targets
- `skip`: 979/2017 (48.5%) of capped scanned targets

### C013 - Agent Card declares usable identity and interface

- `blocked`: 562/2017 (27.9%) of capped scanned targets
- `fail`: 64/2017 (3.2%) of capped scanned targets
- `pass`: 1245/2017 (61.7%) of capped scanned targets
- `warn`: 146/2017 (7.2%) of capped scanned targets

### C020 - Agent answers a spec-conformant SendMessage

- `blocked`: 626/2017 (31.0%) of capped scanned targets
- `fail`: 863/2017 (42.8%) of capped scanned targets
- `pass`: 191/2017 (9.5%) of capped scanned targets
- `skip`: 168/2017 (8.3%) of capped scanned targets
- `warn`: 169/2017 (8.4%) of capped scanned targets

### C021 - Unknown method rejected with JSON-RPC -32601

- `blocked`: 1489/2017 (73.8%) of capped scanned targets
- `fail`: 3/2017 (0.1%) of capped scanned targets
- `pass`: 213/2017 (10.6%) of capped scanned targets
- `skip`: 300/2017 (14.9%) of capped scanned targets
- `warn`: 12/2017 (0.6%) of capped scanned targets

### C022 - Declared streaming support answers a SendStreamingMessage

- `blocked`: 1489/2017 (73.8%) of capped scanned targets
- `fail`: 4/2017 (0.2%) of capped scanned targets
- `pass`: 7/2017 (0.3%) of capped scanned targets
- `skip`: 501/2017 (24.8%) of capped scanned targets
- `warn`: 16/2017 (0.8%) of capped scanned targets

### C023 - Declared HTTP+JSON binding answers a message:send

- `blocked`: 626/2017 (31.0%) of capped scanned targets
- `fail`: 106/2017 (5.3%) of capped scanned targets
- `pass`: 8/2017 (0.4%) of capped scanned targets
- `skip`: 1258/2017 (62.4%) of capped scanned targets
- `warn`: 19/2017 (0.9%) of capped scanned targets

### C030 - Declared security schemes are coherent

- `blocked`: 562/2017 (27.9%) of capped scanned targets
- `fail`: 4/2017 (0.2%) of capped scanned targets
- `pass`: 74/2017 (3.7%) of capped scanned targets
- `skip`: 1280/2017 (63.5%) of capped scanned targets
- `warn`: 97/2017 (4.8%) of capped scanned targets

### C031 - Agent Card signatures are structurally valid JWS

- `blocked`: 562/2017 (27.9%) of capped scanned targets
- `fail`: 1/2017 (0.0%) of capped scanned targets
- `pass`: 57/2017 (2.8%) of capped scanned targets
- `skip`: 1397/2017 (69.3%) of capped scanned targets

### C032 - TLS configuration and certificate posture

- `blocked`: 138/2017 (6.8%) of capped scanned targets
- `pass`: 1871/2017 (92.8%) of capped scanned targets
- `skip`: 6/2017 (0.3%) of capped scanned targets
- `warn`: 2/2017 (0.1%) of capped scanned targets

## Limitations

- **Selection bias runs upward.** Most candidate targets come from directories that health-check their own listings before publishing them, so this population skews toward endpoints that were already known to answer. Nothing here corrects for that.
- **This is the indie long tail, not enterprise deployments.** Publicly discoverable A2A endpoints skew toward solo builders, brokers, and single-page deployments. Enterprise adopters typically sit behind authentication and inside private networks, which a public scanner structurally cannot see (ADR-0018).
- Figures describe the capped, scannable-where-stated subset, not the A2A ecosystem as a whole. Every figure above states its own denominator for exactly this reason.

