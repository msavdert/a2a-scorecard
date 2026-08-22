# ADR-0009: Agent Card JWS signature structural check (C031)

Date: 2026-08-21. Status: accepted.

## Decision

- C031 "Agent Card signatures are structurally valid JWS", stage 3,
  weight 10, requires C011. Like C030 it inspects only the
  already-fetched card and sends no network traffic.
- Scope is structural only. Cryptographic verification is explicitly
  deferred: it needs a crypto dependency (new ADR, CLAUDE.md rule 7)
  and, if keys are fetched from a JWKS URL, arguably a scanning-policy
  entry. Neither lands without the owner's approval. The ROADMAP v0.2
  entry "JWS signature verification" is delivered in this reduced form;
  full verification moves to the ADR-0008 decision round.
- The vendored v1 schema defines `signatures` on the card as an array
  of Agent Card Signature: `protected` (base64url-encoded JSON object,
  required per the spec text), `signature` (base64url, required), and
  an optional unprotected `header` object (RFC 7515 JWS JSON
  serialization).
- Status semantics:
  - SKIP when `spec_generation` is not v1, or `signatures` is absent or
    an empty list: signing a card is optional, and an unsigned card
    must not lose points to a check it never opted into.
  - FAIL when any signature entry is structurally unusable: `signatures`
    itself not a list or an entry not an object; `protected` or
    `signature` missing, empty, not base64url-decodable, or `protected`
    not decoding to a JSON object; a protected header without `alg`; or
    `alg` equal to `none` (an unsigned-JWS marker presented as a
    signature).
  - WARN when every entry decodes but a signature cannot serve its
    public-verification purpose: `alg` is a symmetric MAC family
    (HS256/384/512, verifiable only with a shared secret no client of a
    public card can hold), an alg outside the RFC 7518 / EdDSA
    asymmetric registry, or a protected/unprotected header pair with no
    key-resolution hint at all (none of `jwks`, `jku`, `kid`, `x5c`,
    `x5u`).
  - PASS otherwise: at least one entry, all entries decodable, each
    with an asymmetric registered alg and some key-resolution hint.
- FAIL takes precedence over WARN across entries; evidence names the
  index of each offending entry.

## Rationale

A malformed or alg=none "signature" is worse than no signature: it
advertises an integrity property the card does not have, and a client
that trusts it without verifying is being actively misled. Structure is
what we can honestly judge today without new dependencies or new
traffic, and it already separates the three cases that matter for the
scorecard: unsigned (SKIP), signed correctly in form (PASS), and signed
in a way no client could ever verify (WARN or FAIL).

## Consequences

- Total check weight rises from 120 to 130. Unsigned fixtures SKIP
  C031, so existing test grades are unchanged.
- When cryptographic verification lands later, it becomes a separate
  check (C032+) rather than a widening of C031, so C031's meaning
  stays fixed (CLAUDE.md rule 3).
- The fake agent grows signed-card modes (well-formed, alg=none,
  undecodable protected, symmetric alg, missing key hint) so every
  C031 status path is exercised by tests.
