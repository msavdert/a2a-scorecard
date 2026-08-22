# a2a-scorecard

Independent conformance scanner and (future) public scorecard for A2A
(Agent2Agent) protocol endpoints. Think "SSL Labs for A2A agents".
Not affiliated with the A2A project, Google, or the Linux Foundation.

## Read this first

- Architecture and every non-trivial decision live in `docs/adr/`. Read
  ADR-0005 before touching checks or grading.
- Roadmap and milestone gates: `docs/ROADMAP.md`.
- What the scanner may and may not do on the network: `docs/SCANNING-POLICY.md`.
  That file is policy, not guidance; code must conform to it.
- The vendored A2A spec (JSON Schema + spec text) is in
  `src/a2a_scorecard/vendor/` with its update procedure in `PROVENANCE.md`
  there. Answer spec questions from the vendored copy, not from memory.

## Architecture map

- `src/a2a_scorecard/checks/` - one module per check family. A check is a
  `Check` subclass with ClassVar `check_id`, `title`, `stage`, `weight`,
  `requires`. It is registered in `checks/__init__.py:ALL_CHECKS`.
- `scan.py` - orchestrator. Runs checks ordered by (stage, check_id);
  a check whose `requires` did not end PASS/WARN is reported BLOCKED
  without executing.
- `grading.py` - score and letter-grade math (ADR-0005).
- `schema.py` - validates cards against the vendored official JSON Schema;
  the ref-resolution trick is documented in its docstring and ADR-0004.
- `tests/conftest.py` - in-process fake agent; the only HTTP server tests
  may talk to.

## Hard rules

1. Probes must be harmless. Never add a check that sends exploit payloads,
   attempts auth bypass, floods a target, or mutates remote state beyond the
   single benign SendMessage ping. Auth-gated endpoints are reported as
   auth-gated, never probed behind the gate.
2. Tests never touch the network. Every HTTP request in the test suite goes
   to the in-process fake agent on 127.0.0.1.
3. Check IDs (C001, C010, ...) are permanent once released: never renumber,
   rename, or reuse an ID. Retire a check by removing it from ALL_CHECKS and
   recording the retirement in an ADR.
4. Changing grading semantics, check weights, or probe behavior requires a
   new ADR file and updated tests in the same commit.
5. `make check` (ruff + mypy + pytest) must be green before every commit.
   Never commit a red tree.
6. Files under `src/a2a_scorecard/vendor/` are upstream copies: never
   hand-edit them. Update only via the procedure in `vendor/PROVENANCE.md`.
7. No new runtime dependencies without an ADR. Current set: httpx,
   jsonschema, referencing. Stdlib first.
8. No emoji anywhere in the repository.
9. Nothing in this repo may imply official A2A or Linux Foundation
   affiliation. Keep the independence disclaimer in README intact.
10. This repository is private until the ROADMAP v0.4 gate. Do not publish,
    mirror, or change visibility without the owner's explicit instruction.
11. Never commit or push unless the owner asked for it in the session.

## Everyday commands

    make install     # uv sync
    make check       # lint + typecheck + test; the pre-commit bar
    make test        # pytest only
    uv run a2a-scorecard scan <url>          # scan a real endpoint
    uv run a2a-scorecard scan <url> --json   # machine-readable report
