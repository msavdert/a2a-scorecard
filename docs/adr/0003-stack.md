# ADR-0003: Stack - Python 3.12+, uv, httpx, jsonschema, stdlib elsewhere

Date: 2026-08-21. Status: accepted.

## Decision

- Python >= 3.12, packaged with uv + hatchling, src layout.
- Runtime dependencies capped at three: httpx (HTTP client),
  jsonschema + referencing (draft 2020-12 validation of the vendored spec
  schema). Everything else is stdlib: dataclasses for models (no pydantic),
  argparse for the CLI (no click/typer).
- Tooling: ruff (lint + format), mypy --strict, pytest. One entry point:
  `make check`.

## Rationale

The maintainer of record is an AI agent session that changes over time;
the smaller the dependency and idiom surface, the smaller the chance a
future session misuses it. Python was chosen over Go/TypeScript because
the A2A reference ecosystem is Python-first (a2a-python is the most mature
SDK), making cross-checking against reference behavior cheapest there.

## Consequences

- Adding any runtime dependency requires a new ADR (CLAUDE.md rule 7).
- If scan concurrency ever matters (v0.3 batch mode), prefer
  httpx's async client over adding a framework.
