# ADR-0014: REST binding probe check (C023)

Date: 2026-08-21. Status: accepted.

## Decision

- C023 "Declared HTTP+JSON binding answers a message:send", stage 2,
  weight 10, requires C013. It sends the single REST ping that
  ADR-0008 added to SCANNING-POLICY: one benign, self-identifying
  `POST {interface url}/message:send` with the same message text as
  the JSON-RPC ping, only when the JSON-RPC pings were not applicable,
  so a scan never sends more than two message pings in total.
- C023 deliberately requires C013, not C020: ADR-0005's dependency
  rule cascades a SKIP, and C020 SKIPs exactly on the non-JSONRPC
  agents C023 exists to cover.
- Status semantics:
  - SKIP when the card declares no `HTTP+JSON` entry in
    `supportedInterfaces`, or when a JSON-RPC interface was applicable
    (C020's outcome is not SKIP): those agents were already probed on
    their preferred binding, and a second binding's ping would exceed
    the policy budget.
  - WARN when the REST endpoint answers 401/403: recorded as
    auth-gated, never probed further, mirroring C020's judgment call
    (ADR-0005).
  - PASS when the response is 200 with a JSON body recognizable as a
    spec response object (Message or Task shape).
  - WARN also when the endpoint answers 200 but the body is not
    recognizable as a spec response: reachable but drifted.
  - FAIL on any other status, a connection failure, or an unparseable
    body: the card promised an HTTP+JSON binding and the wire does
    not deliver one.
- One request, no retries, no fallback paths. Unexpected exceptions
  degrade to an evidenced FAIL, not ERROR.

## Rationale

Since ADR-0005, agents declaring only non-JSONRPC bindings are graded
on card quality alone, with C020/C021 SKIP - a documented gap. C023
closes the HTTP+JSON half of it with the minimum traffic the policy
allows, ending the era where a REST-only agent could score well
without ever answering a message. GRPC-only agents remain
card-only-graded; probing GRPC needs a dependency and its own ADR, and
stays future work.

## Consequences

- Total check weight rises from 150 (after C022, ADR-0013) to 160.
  Fixtures with a JSONRPC interface SKIP C023, so existing grades are
  unchanged.
- The fake agent grows REST modes (rest-only happy path, rest-only
  drift, rest-only rejection, rest-only auth-gated) whose cards
  declare only `HTTP+JSON`, so every status path is exercised.
- The scorecard's `spec_generation`/binding story is now: JSONRPC
  probed by C020/C021/C022, HTTP+JSON by C023, GRPC declared-only.
