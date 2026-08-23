# ADR-0021: Dataset record format v1, and how methodology changes are survived

Date: 2026-08-22. Status: accepted.
Answers the question ADR-0011 raises and leaves open.

## Context

ADR-0011 made the longitudinal dataset the project's primary long-term
product and required every record to be stamped with scanner version,
grading methodology version and spec version so any historical grade can
be reproduced and explained. ADR-0018 promoted it further: with the
per-agent scorecard retired, the dataset is no longer the input to the
product, it is the product. What ADR-0011 did not settle is what happens
when the check set itself changes - a check retired, a check added, a
weight adjusted - which over a multi-year series is not an edge case but
the normal condition.

The census exposed the concrete failure mode. Its harness stored
`checks: {check_id: status}` and thereby discarded the per-check weights.
Everything downstream still worked, because the weights were recoverable
from the source tree at that commit - which is exactly the kind of
dependency that quietly rots. Two years and three retired checks later,
those records would be unrescorable.

## Decision

### One file per run, self-delimiting

`data/runs/run-YYYYMMDDTHHMMSSZ.jsonl`, three record types in order: one
`run_start` header, N `target` records, one `run_end` footer. **Absence
of the footer means the run is incomplete**, which is what makes resume
decidable without a side-channel.

One file per run rather than one appended file, because a monthly cron
commits results into git: git stores whole blobs, so appending to a
shared file re-stores it every month while per-run files store exactly
the increment. It also removes the textual conflict between a manual
dispatch and the cron, keeps resume a plain append, and makes honouring a
late opt-out a per-file redaction rather than a rewrite of one large
blob.

A regenerated `data/index.json` maps runs and carries `last_scanned_at`
per target, which is also what enforces the daily re-scan floor.

### The report is stored verbatim

Each `target` record embeds `TargetReport.to_dict()` **unprojected** -
every check's status, weight, evidence and details. Evidence is already
bounded to 500 characters, so record size is bounded by construction.

This is the direct lesson from the census harness. Storing a status map
is a projection that silently makes the corpus dependent on a source tree
to interpret. Storing the full result makes each row self-describing, and
self-describing rows are the only kind that survive being extracted,
concatenated and joined across years.

Card bodies are not stored in v0.3. The policy permits it, but it bloats
every commit for marginal gain, and it can be added later without
invalidating existing records.

### Every row carries its own methodology stamp

`scanner_version`, `grading_version`, `spec_version` and
`grading_manifest_digest` are repeated on every `target` record even
though the header holds them. Roughly sixty bytes to keep a row
interpretable after it has been separated from its file, which is what
happens to rows.

`spec_version` needs a single source of truth: a `SPEC_VERSION` constant
beside the schema resource, with a test asserting it agrees with the
vendored filename and with `vendor/PROVENANCE.md`. Records carry that
constant verbatim, `v`-prefix included, so the stamp and the vendored
filename can never drift into two spellings of the same version.

### The methodology manifest digest

`grading_manifest_digest` is a sha256 over canonical JSON of
`[{check_id, weight}]` sorted by check id, derived from `ALL_CHECKS`.
Titles and stages are excluded deliberately: they are cosmetic, and a
typo fix in a title must not read as a methodology change.

This is the field that answers ADR-0011's open question. It makes "the
ruler changed" detectable at row level, by anyone, without access to the
source tree that produced the row.

The reader contract, which is part of this decision and not an
implementation note:

- An absent `check_id` in a record means "not part of the methodology
  that produced this record". It is never a failure, never a null, and
  must never be imputed.
- Cross-run comparison is valid only within an equal
  `grading_manifest_digest`, or after explicit rescoring.
- Because every record carries status *and* weight per check, any
  historical scan can be rescored under any later methodology. Retiring a
  check therefore never invalidates history: the new series is computed
  and the old series is retained. This repository already relies on that
  property - the census analysis recomputes outcomes from stored
  per-check data rather than trusting the labels written at capture time.

**No historical record is ever rewritten.** Files are append-only and
past run files are immutable. The single exception is redaction on an
opt-out request, which removes records rather than altering them.

### CI guards

A committed golden `docs/methodology/grading-1.json` for the current
`GRADING_VERSION`. A test fails if the computed digest differs from the
golden, naming the two legal remedies: regenerate the golden, which is
legal only before the first published dataset, or bump `GRADING_VERSION`
and add `grading-<n>.json`. After the first release, a second assertion
freezes it: the digest recorded in any committed run header must still
match the golden for that version.

The same module carries the check-ID uniqueness guard. CLAUDE.md rule 3
has forbidden renumbering and reuse since v0.1 and nothing has ever
enforced it; a rule that only exists in prose is a rule that will be
broken by a future contributor who has not read the prose.

## Consequences

- New `dataset.py` (writer plus readers) and `methodology.py`;
  `SPEC_VERSION` added to `schema.py`; `docs/methodology/grading-1.json`
  committed.
- The writer fsyncs each record. The census writer flushed without
  fsync, which loses the tail on a killed runner - acceptable for a
  research script, not for the product.
- Resume discards a trailing unparseable line as a torn write, truncates
  to the last good newline, and continues; completed targets are skipped
  without issuing a request.
- Tests cover the round trip, the torn-tail rule, the digest guard, the
  ID-uniqueness guard, and that every written record carries all four
  stamps.
