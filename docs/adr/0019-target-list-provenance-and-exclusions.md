# ADR-0019: Target list format, mandatory provenance, and the exclusion list

Date: 2026-08-22. Status: accepted.
Supersedes ROADMAP.md's "target list format (YAML)". Implements the
opt-out promise in docs/SCANNING-POLICY.md.

## Context

Unattended batch scanning (ADR-0018) needs a committed list of what to
scan and a committed list of what never to scan. ROADMAP v0.3 specified
YAML for the first. Two policy lines constrain both:

- SCANNING-POLICY "What we scan": only endpoints publicly advertised as
  A2A agents. Provenance is therefore a **precondition for scanning**,
  not documentation.
- SCANNING-POLICY "Opt-out": opt-outs are honored **permanently**.

## Decision

### Format: JSONL, not YAML

PyYAML would be a new runtime dependency, which CLAUDE.md rule 7 forbids
without an ADR, and it buys only comments. `tomllib` is stdlib but
read-only, and v0.3 includes a harvester that must *write* the list;
hand-rolling a TOML serialiser to satisfy a format preference is worse
than the problem it solves. JSONL is stdlib in both directions, gives a
one-line git diff per target added or removed, and is already this
repository's data idiom. Its only weakness - no comments - is covered by
a `notes` field and a reader that skips blank and `#`-prefixed lines.

`data/targets.jsonl`, one record per line:

    {"target": "https://agent.example.com",
     "operator": "example.com",
     "sources": [{"directory": "a2a-registry.org",
                  "ref": "https://a2a-registry.org/agents/example",
                  "kind": "registry",
                  "observed_at": "2026-08-20"}],
     "first_seen": "2026-08-20",
     "tags": ["census-2026-08-22"],
     "notes": ""}

- `target_id`, the join key across years, is the normalised form:
  lowercased scheme and host, default port dropped, no trailing slash.
  Normalisation lives in one tested function; a dataset whose join key
  drifts is not a longitudinal dataset.
- `operator` defaults to the derived operator unit, productised from the
  census sampler **including its PaaS-suffix table**. That table encodes
  real knowledge - that each `*.vercel.app` tenant is a distinct owner -
  and must be carried over rather than re-derived.

### Provenance is required and enforced at load

`sources` must be present and non-empty. **The loader raises on an entry
without it.** This is the point of the ADR: the policy says we only scan
publicly advertised endpoints, and an unprovenanced entry is not a
warning to be logged in an unattended run, it is an entry we are not
permitted to scan. Hard-failing the load is what turns that policy line
from aspiration into something the machine enforces at 03:00 with nobody
watching.

### Exclusions live in their own file

`data/exclusions.jsonl`:

    {"pattern": "example.com", "scope": "domain",
     "reason": "owner request", "requested_by": "github:@someuser",
     "issue": "https://github.com/msavdert/a2a-scorecard/issues/42",
     "effective_from": "2026-09-01", "permanent": true}

- `scope` is `url`, `host`, or `domain`. **An owner request defaults to
  `domain`**: someone asking to be removed means their whole estate, not
  the one hostname we happened to list.
- A separate file rather than deleting the target-list entry, because the
  harvester rewrites `targets.jsonl` from public directories every run.
  A deleted entry silently resurrects next month, which would quietly
  break "permanently". The exclusion list is authoritative and is applied
  after every load.
- Enforced in three places: inside the loader so no caller can forget, in
  the batch runner as a redundant assertion, and in the single-URL `scan`
  CLI path, which refuses an excluded URL and exits non-zero. There is no
  `--force`. "Permanently" means there is no override, including for us.
- Each run header records the exclusion file's digest and how many
  entries were applied, so any published run can be audited for opt-out
  compliance after the fact rather than on trust.

## Consequences

- New `targets.py` and `sampling.py`; `data/targets.jsonl` seeded from
  the census candidate set; an initially empty `data/exclusions.jsonl`.
- ROADMAP.md's YAML line is edited in the same commit.
- Tests cover normalisation, operator derivation, the provenance
  hard-failure, all three exclusion scopes, and seeded sampling
  determinism.
