# ADR-0010: TLS posture check (C032)

Date: 2026-08-21. Status: accepted.

## Decision

- C032 "TLS configuration and certificate posture", stage 3, weight 10,
  requires C001. It performs the single bare TLS handshake that
  ADR-0008 added to SCANNING-POLICY: one connection to the target's
  host and port with the stdlib `ssl` default (secure) client context,
  reading the negotiated protocol version and the presented
  certificate, then closing. No HTTP request rides on it, and there
  are never additional handshakes with downgraded configurations.
- Status semantics:
  - SKIP when the target URL scheme is not https (only reachable in
    local development and tests, where `allow_http` lets C001 WARN).
  - FAIL when the handshake with the default context fails (protocol
    negotiation failure, certificate verification failure, hostname
    mismatch), or when the negotiated version is below TLS 1.2. C001
    having already succeeded over HTTPS makes this rare; evidence
    carries the ssl error string.
  - WARN when the handshake succeeds but the certificate expires
    within 14 days: valid today, an outage waiting to happen.
  - PASS when the negotiated version is TLS 1.2 or newer and the
    certificate is valid with more than 14 days of life. The
    negotiated version, cipher, and days-to-expiry are recorded in
    details either way.
- The handshake lives in a module-level function taking host, port,
  and timeout and returning a small result object. Unit tests
  monkeypatch that function to exercise FAIL/WARN/PASS; the SKIP path
  runs against the plain-http fake agent. This is the one check whose
  probe cannot be exercised end-to-end by the in-process fake agent
  (it serves plain HTTP), and the seam is the explicit, tested
  boundary instead.

## Rationale

Transport security is the floor of the scorecard's security stage: an
agent card can promise any auth scheme, but every credential crosses
this handshake first. Reading the negotiated parameters of one honest
handshake is the strongest statement we can make without downgrade
probing, which ADR-0008 deliberately rules out - SSL Labs-style
capability enumeration is out of scope for a scanner that promises to
send only what a well-behaved client would.

The 14-day WARN threshold matches the shortest common automated
renewal cadence (ACME renews at 30 days before expiry; less than 14
days left means renewal is already broken or manual).

## Consequences

- Total check weight rises from 130 to 140. Plain-http test fixtures
  SKIP C032, so existing fixture grades are unchanged.
- `ssl` joins the stdlib modules the scanner depends on; no new
  runtime dependency.
- If a future ADR ever wants downgrade probing, it must first amend
  SCANNING-POLICY again; C032's meaning stays fixed either way.
