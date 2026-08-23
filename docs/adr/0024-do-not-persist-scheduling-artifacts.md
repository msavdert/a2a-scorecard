# ADR-0024: Do not persist scheduling artifacts, and do not commit an empty run

Date: 2026-08-23. Status: accepted.
Amends ADR-0020's outcome taxonomy and ADR-0021's record rules.

## Context

The first dispatch of the monthly workflow after the first real run
produced a 1.6 MB run file containing 2,479 records, every one of them
`skipped_recent` with `report: null` and `elapsed_s: 0.0`. The run
measured nothing - the daily re-scan floor correctly declined to scan
anything, because a full run had completed twenty minutes earlier - and
then committed a file recording that nothing happened, 2,479 times.

ADR-0020 said every outcome is "recorded verbatim per target", and
ADR-0021 said the writer is called for absences too. That is right for
some absences and wrong for this one, and the distinction was not drawn
because until there was a real dataset there was nothing to notice.

On the real monthly cadence this would never fire - a month is longer
than the one-day floor. It fires on a same-day re-dispatch, on a retry
after a failure, and on any manual run, which are exactly the situations
where someone is already dealing with a problem and does not need 1.6 MB
of noise committed on top of it.

## Decision

**`skipped_recent` is not written to the dataset.** It is counted in the
run summary and printed, and that is all.

The distinction that ADR-0020 should have drawn: an absence is worth
persisting when it records something about the *target* or about a
*decision we made about that target*.

- `excluded` - a policy fact. An opt-out needs an audit trail; a row
  saying "we did not scan this, deliberately" is the evidence.
- `throttled`, `error`, `budget_exceeded`, `deadline_exceeded`,
  `skipped_throttled_group` - facts about what happened when we tried.
- `skipped_recent` - a fact about *our scheduler's clock*, not about the
  target. It says only that we ran twice in one day. The run index
  already records when each target was last scanned, so the information
  is not lost; it was never in the target record to begin with.

**A run that produced no target records does not leave a file.** The CLI
removes it rather than committing a header and footer wrapped around
nothing.

## Consequences

- `run_batch` counts `skipped_recent` in the summary without calling the
  writer; the CLI deletes a run file that ends with zero target records,
  and the workflow therefore finds nothing to commit.
- `run-20260823T031623Z.jsonl` is deleted from the repository. ADR-0021
  says past run files are immutable and never rewritten, and that rule
  stands - but it protects records of measurement, and this file contains
  none. It is a defect artifact produced twenty minutes before its own
  deletion, not a historical record of what the ecosystem looked like.
  Deleting it is the same category of act as this ADR: correcting
  something that recorded nothing.
- Tests pin both behaviours: a batch where every target is skipped writes
  no records and leaves no file, and an excluded target still does write
  its row.
