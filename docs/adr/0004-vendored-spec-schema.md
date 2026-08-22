# ADR-0004: Vendor the official spec schema; resolve refs by title-flattening

Date: 2026-08-21. Status: accepted.

## Context

The A2A project does not commit its JSON Schema to git; it is a build
artifact generated from `specification/a2a.proto` and published at
`https://a2a-protocol.org/latest/spec/a2a.json`. The bundle keys its 47
definitions by human title ("Agent Card") while `$ref`s use proto-derived
relative URIs (`lf.a2a.v1.AgentCard.jsonschema.json`,
`google.protobuf.Struct.jsonschema.json`). Flattening a title by removing
its spaces reproduces the PascalCase name in those URIs exactly (verified
across all 47 definitions at v1.0.1, including `OAuth2SecurityScheme` and
`AuthorizationCodeOAuthFlow`).

Because the schema is proto3-derived, it marks no field as required; its
teeth are types and `additionalProperties: false`. Presence requirements
are therefore enforced by a separate semantic check (C013), not by schema
validation.

## Decision

- Vendor the published bundle and the spec markdown under
  `src/a2a_scorecard/vendor/` (packaged with the wheel), never hand-edited.
- `schema.py` resolves refs with a `referencing.Registry` retrieve hook:
  strip `.jsonschema.json`, take the last dotted segment, look up the
  definition whose space-stripped title matches.

## Update procedure (on a new A2A spec release)

1. Download `https://a2a-protocol.org/latest/spec/a2a.json` and
   `docs/specification.md` at the release tag from a2aproject/A2A.
2. Save as `a2a-vX.Y.Z.json` / `specification-vX.Y.Z.md`; update
   `SCHEMA_RESOURCE` in schema.py; record the new version, source URLs and
   retrieval date in `vendor/PROVENANCE.md`.
3. Run `make check`; fix fixtures only if the spec genuinely changed, and
   note behavior changes in a new ADR. Keep the previous vendored version
   during a transition if dual validation is needed (ROADMAP v0.5).
