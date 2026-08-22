# Scanning policy

This file is binding on all code in this repository. A check or feature
that cannot be implemented within these rules does not get implemented.
Changes to this policy require an ADR and the owner's explicit approval.

## What we scan

- Only endpoints that are publicly reachable and publicly advertised as A2A
  agents (listed in a public directory, registry, Agent Card, or
  documentation).
- Never internal, private, or incidentally discovered endpoints.

## How we identify ourselves

- Every request carries the User-Agent
  `a2a-scorecard/<version> (conformance scanner; <repo URL>)` with a working
  contact path (GitHub issues).
- We never disguise the scanner as a browser or another agent.

## What a scan sends

- Read-only HTTP GETs of public discovery documents.
- At most one benign, spec-conformant `SendMessage` ping whose text
  identifies itself as a conformance probe.
- One request with an unknown method name to observe error handling.
- Never: exploit payloads, prompt-injection attempts, auth bypass or
  credential guessing, fuzzing, or requests designed to consume meaningful
  compute on the target.
- Auth-gated endpoints (401/403) are recorded as auth-gated and not probed
  further.

## Volume and pacing

- A single scan sends fewer than 10 requests to a target.
- Batch scanning serializes requests per host and honors HTTP 429 and
  Retry-After. Re-scan frequency for the public scorecard: at most daily
  per target.

## Opt-out

- Endpoint owners can request removal via a GitHub issue; opt-outs are
  honored permanently in an exclusion list committed to this repo.

## Data handling

- We store protocol metadata only: check results, status codes, timings,
  card contents (which are public documents). We do not store message
  content beyond our own ping and its direct reply.

## Incidental findings

- If a scan incidentally reveals a serious vulnerability in a specific
  target, we disclose privately to the endpoint owner and do not publish
  the detail on the scorecard.
