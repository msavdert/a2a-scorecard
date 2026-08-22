# ADR-0007: Stage 3 opens with security-scheme sanity check (C030)

Date: 2026-08-21. Status: accepted.

## Decision

- Stage 3 (security), reserved since ADR-0005, gets its first check:
  C030 "Declared security schemes are coherent", weight 10, requires C011.
- C030 inspects only the already-fetched Agent Card. It sends no network
  traffic of its own, so it fits inside the existing SCANNING-POLICY
  bounds without amending them.
- Status semantics:
  - SKIP when the card declares no security information at all (neither
    `securitySchemes` nor `securityRequirements`), or when
    `spec_generation` is not v1 (the sanity rules below are written
    against the v1 card shape). The requirements field is named
    `securityRequirements` in the vendored JSON schema; the spec's
    markdown text calls it `security`, and the schema wins (ADR-0004).
  - FAIL when a scheme name referenced from `securityRequirements` is
    not declared in `securitySchemes`, or when a declared scheme is
    missing the fields a client needs to actually execute that scheme
    type. The official schema cannot catch either: proto3 marks nothing
    required (ADR-0004). The per-type field list is derived from the
    vendored scheme definitions and the OpenAPI Security Scheme Object
    they cite, and lives in `checks/security.py`.
  - WARN when declarations are legal but weak: any auth-related URL
    (OAuth2 authorization/token endpoints, `openIdConnectUrl`) served
    over plain HTTP, or a scheme object whose type is unrecognized by
    the vendored v1 spec.
  - PASS otherwise. Schemes that are declared but never referenced from
    `securityRequirements` are recorded in details as informational,
    not penalized.
- Field names and per-type requirements come from the vendored spec
  (`src/a2a_scorecard/vendor/`), never from memory.

## Rationale

The v0.2 roadmap lists five new checks. Three of them (TLS posture,
streaming probe, REST binding probe) add new traffic to a scan and
therefore need a SCANNING-POLICY amendment, which requires the owner's
explicit approval per that file's own header. Security-scheme sanity is
the one check that deepens the security stage using data the scanner
already holds, so it lands first. A card that gates its endpoint behind
auth it never coherently declares is exactly the kind of silent
interop failure the scorecard exists to surface: a client cannot
authenticate against a scheme that is referenced but not defined.

## Consequences

- Stage 3 numbering starts at C030; later stage-3 checks take C031+ with
  the usual gaps. C030 is permanent once released (CLAUDE.md rule 3).
- Total check weight rises from 110 to 120. For targets whose card
  declares no security, C030 is SKIP and scores are unchanged, so v0.1
  fixtures keep their grades.
- The fake agent grows modes with security declarations (coherent,
  dangling reference, plain-http auth URL, malformed scheme) so every
  C030 status path is exercised by tests, per the v0.2 gate.
