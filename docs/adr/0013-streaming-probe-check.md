# ADR-0013: Streaming probe check (C022)

Date: 2026-08-21. Status: accepted.

## Decision

- C022 "Declared streaming support answers a SendStreamingMessage",
  stage 2, weight 10, requires C020. It sends the single streaming
  request that ADR-0008 added to SCANNING-POLICY: one JSON-RPC
  `SendStreamingMessage` ping (same benign, self-identifying message
  body as C020's ping) to the target's JSON-RPC endpoint, expecting an
  SSE response (`Content-Type: text/event-stream`, spec section 9.4.2).
  The connection closes after the first SSE data event or 10 seconds,
  whichever comes first.
- Applicability follows the card: the spec says agents whose
  `capabilities.streaming` is false or absent MUST reject streaming
  operations, so probing them would test a capability they never
  claimed.
- Status semantics:
  - SKIP when the card does not declare `capabilities.streaming: true`,
    when C020 ended auth-gated (the policy forbids probing behind the
    gate, so the WARN that C020 records for 401/403 must not be
    treated as a green light here), or when no JSON-RPC endpoint is
    applicable (same non-JSONRPC-binding rule as C020/C021).
  - PASS when the response is an SSE stream and the first data event
    arrives within the bound and parses as a JSON-RPC response object.
  - WARN when the endpoint accepts the method but the response is not
    a stream (a plain JSON-RPC response with 200: functional drift -
    the client asked for a stream and got a unary reply), or when the
    first event arrives but is not parseable JSON-RPC.
  - FAIL when the declared-streaming endpoint rejects the method
    (error response, including method-not-found), returns a non-200,
    or the connection ends or times out before any data event: the
    card promised streaming and the wire does not deliver it.
- The 10-second bound and single-request limit are policy, not
  tunables: the probe never retries, never opens a second stream, and
  never reads past the first data event.

## Rationale

Streaming is the capability most likely to silently rot: it takes an
event loop and connection handling that unary request paths never
exercise, and a card that advertises it falsely breaks every client
that picks the streaming transport first. One bounded request
distinguishes the three cases the scorecard cares about - works,
answers-but-not-streaming, and rejected - without holding a
connection longer than a well-behaved client's first-token timeout.

## Consequences

- Total check weight rises from 140 to 150. Fixtures whose cards do
  not declare streaming SKIP C022, so existing grades are unchanged.
- The fake agent grows streaming modes (SSE happy path, unary-reply
  drift, method rejection, never-sends-an-event timeout with a short
  test-side bound) so every status path is exercised without real
  network access; the 10-second production bound comes from Settings
  so tests can shrink it.
- The probe reuses C020's message construction so the two pings stay
  textually identical apart from the method name; if C020's ping text
  changes, C022 follows automatically.
