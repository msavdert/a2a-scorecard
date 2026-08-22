# Tier-1 mechanical audit prompt for omp delegates

Usage (from the operator's omp-fleet skill; run from the repo root):

    mkdir -p .audit/<date>
    # copy the PROMPT block below into .audit/<date>/prompt.txt
    $OMP_RUN audit-<date> "$PWD/.audit/<date>/prompt.txt"

Model: the omp-fleet skill's default fact/extraction model. Findings that
come back are CLAIMS - verify each file:line in source before acting
(docs/REVIEW-POLICY.md tier 1).

---PROMPT---

You are auditing the repository in the current working directory
(a2a-scorecard, a conformance scanner for the A2A protocol). This is a
MECHANICAL cross-check, not a design review. Do exactly the five tasks
below by reading files; do not give advice, do not propose refactors,
do not judge design choices.

1. Consistency of grading constants: compare the weights, statuses,
   score formula and letter bands stated in
   docs/adr/0005-check-architecture-and-grading.md against the actual
   code in src/a2a_scorecard/grading.py, src/a2a_scorecard/models.py and
   the weight/stage/requires ClassVars in src/a2a_scorecard/checks/*.py.
   Report every mismatch.
2. Doc/code drift: compare every factual claim about scanner behavior in
   README.md, CLAUDE.md and docs/SCANNING-POLICY.md (request counts,
   probe methods, grade bands, check list) against the code. Report every
   statement that no longer matches.
3. Test coverage inventory: for each Check subclass in
   src/a2a_scorecard/checks/, list the CheckStatus values its run() can
   return, and for each value whether any test in tests/ asserts that
   check ending in that status. Output a table: check_id, status,
   covered yes/no, test name or "-".
4. Spec cross-check: compare the JSON-RPC method names, field names and
   enum values used in src/a2a_scorecard/checks/protocol.py and
   tests/conftest.py against the vendored spec text in
   src/a2a_scorecard/vendor/specification-v1.0.1.md (grep it; do not read
   it whole). Report every name the spec does not support.
5. Registry consistency: confirm every Check subclass defined under
   src/a2a_scorecard/checks/ appears exactly once in ALL_CHECKS in
   checks/__init__.py, and that no two checks share a check_id.

TOOLS: read and write files only. Do NOT launch subagents and do NOT use
the task tool - you are a single process. Do NOT run shell commands, do
NOT write scripts, do NOT use the network.

RULES:
- Every reported mismatch gets file path and line number for BOTH sides
  of the mismatch where applicable.
- Label each finding VERIFIED (you read both locations) - anything you
  could not fully read, omit.
- If a symbol does not literally appear in the vendored spec files, its
  row is NOT-FOUND, never VERIFIED - even when you believe it is correct
  for historical or external reasons. (A pilot run labeled a name
  VERIFIED at a line that does not contain it; that is the exact failure
  this rule exists to prevent.)
- Markdown tables. No advice, no praise, no padding. Findings only.
- End with a COVERAGE section: which of the five tasks you completed
  fully, which partially, and what you could not read.

OUTPUT: Write the full report to ./.audit/<date>/report.md. Then reply
with AT MOST 5 lines: number of mismatches per task, nothing else.
