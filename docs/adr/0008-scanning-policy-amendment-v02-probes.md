# ADR-0008: Scanning-policy amendment for TLS, streaming, and REST probes

Date: 2026-08-21. Status: accepted - approved by the owner in session on
2026-08-21, as the SCANNING-POLICY header requires.

## Context

Three of the five v0.2 checks send traffic that the current
"What a scan sends" list in docs/SCANNING-POLICY.md does not enumerate:

- TLS posture needs one additional TLS handshake to the target host to
  read the negotiated protocol version and certificate metadata (httpx
  does not expose these from the connection C001 already made).
- The streaming probe opens one SSE response, which is a long-lived
  connection the policy currently has no bound for.
- The REST binding probe sends one `POST /v1/message:send`, a message
  send outside the two JSON-RPC pings the policy currently allows.

## Decision (proposed)

Amend "What a scan sends" with three items, and code to them:

1. One TLS handshake to the target's host and port that carries no HTTP
   request. It reads only the negotiated protocol version and the
   certificate presented; it never tests for weak-protocol acceptance by
   retrying with downgraded client configurations.
2. At most one streaming request per scan, only to targets whose card
   declares streaming support. The connection is closed after the first
   data event or 10 seconds, whichever comes first, and its content is
   handled under the existing data-handling rules (our ping and its
   direct reply only).
3. At most one benign REST `message:send` ping per scan, sent only to
   targets whose card declares an HTTP+JSON interface and only when the
   JSON-RPC pings were not applicable, so the total number of message
   pings per scan stays at two. The ping text identifies itself as a
   conformance probe, same as the JSON-RPC pings.

The overall bound tightens accordingly: a single scan sends fewer than
10 requests plus at most one bare TLS handshake, and at most one of the
message pings may be streaming.

## Rationale

Each addition is the minimum traffic that makes its check honest. The
alternative for TLS (introspecting the pooled httpx connection) depends
on httpx internals that are not public API; a bare handshake is simpler
and observable by the target as exactly what it is. The streaming bound
exists so a scan can never hold a connection open longer than the
existing request timeout order of magnitude. Capping message pings at
two total, regardless of binding, keeps the policy's most sensitive
number unchanged.

## Consequences

- If approved: SCANNING-POLICY.md "What a scan sends" and "Volume and
  pacing" are updated in the same commit that flips this ADR to
  accepted, before any of the three checks is implemented.
- If rejected or narrowed: the affected checks are dropped from v0.2 or
  reshaped to fit whatever bound the owner sets; the roadmap entry is
  updated in the same commit.
- Until then, v0.2 proceeds only with checks that stay inside current
  policy (C030, ADR-0007, and the card-structural part of JWS
  verification).
