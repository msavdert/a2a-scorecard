# Review policy - three tiers

Rationale: ADR-0006. The goal is catching wrong-verdict bugs without
spending premium-model quota on every commit.

## Tier 0 - deterministic, every commit (free)

`make check`: ruff, mypy strict, pytest. Mandatory before every commit
(CLAUDE.md rule 5). Anything checkable deterministically belongs here,
not in a model review: prefer adding a test or a lint rule over asking
any model to re-verify the same property repeatedly.

## Tier 1 - omp mechanical audit (cheap, off-quota)

A delegated cross-check run on omp (weaker models, separate subscriptions;
see the operator's omp-fleet skill). Prompt template:
`tools/omp-audit-prompt.md`. It is limited to comparison work: code vs
ADR constants, code vs README/policy claims, code vs the vendored spec
text, test coverage inventory per check status path.

When: before pushing a batch of work that touched `src/`, and at least
once per milestone.

Rules:
- Delegate output is a CLAIM, not a finding. Verify each file:line in
  source before acting; discard anything unverifiable.
- Findings must come back as a table with file:line references; a run
  that returns prose advice is a failed run.
- Never send judgment questions to omp (design, semantics, "is this
  approach right") - wrong tier.
- Work dir is `.audit/` (gitignored); keep the raw report there as
  provenance until the milestone closes.

## Tier 2 - Claude reviewer subagent (expensive, reserved)

An independent Claude `reviewer` agent pass over the diff, as done for the
initial commit (it found the gRPC-only false-FAIL bug - the class of
finding tier 1 cannot produce).

When (all mandatory):
- at each ROADMAP milestone completion, on the milestone's whole diff;
- before the v0.4 public-launch gate, on the full tree;
- after any change to grading semantics or the probe engine
  (`grading.py`, `scan.py`, `checks/protocol.py`) beyond mechanical edits.

Not per-commit. Between milestones, tiers 0-1 carry the load.
