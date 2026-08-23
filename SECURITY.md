# Security, scanning, and how to be excluded

This project runs an automated conformance scanner against publicly
advertised A2A agent endpoints. If one of those is yours, this file is
the short version of what we do and how to make us stop.

## If you want your endpoint excluded from scanning

Open an issue titled `opt-out: <your domain>`. You do not need to explain
why, and you do not need to prove ownership of a publicly advertised
endpoint to be removed from a list of publicly advertised endpoints.

What happens:

- The exclusion is committed to `data/exclusions.jsonl` and applied
  before every run from then on. It is permanent - there is no override
  flag, including for us.
- By default it covers your whole domain and every subdomain, not just
  the one hostname we happened to list. Say so if you want a narrower
  scope.
- Any records already in the published dataset are removed on request.
  Ask for that in the same issue if you want it.

## If you think a result about your endpoint is wrong

Open an issue with the URL. Grades are reproducible: every record in
`data/runs/` carries the scanner version, the grading methodology digest
and the full per-check result including evidence, so a disagreement can
be settled by looking rather than by arguing.

We would rather hear about a false result than not. The scanner has had
at least one defect that produced systematically wrong results across
hundreds of targets (ADR-0016), and it was found by measurement, not by
reasoning about the code.

## What a scan does

The binding rules are in `docs/SCANNING-POLICY.md`. In summary, a single
scan sends fewer than ten requests: read-only GETs of your public
discovery documents, at most two benign `SendMessage` pings whose text
identifies itself as a conformance probe, one request with an unknown
method name to observe error handling, and one bare TLS handshake.

It never sends exploit payloads, prompt-injection attempts, auth bypass
or credential guessing, or fuzzing. If your endpoint returns 401 or 403
it is recorded as auth-gated and not probed further. Every request
carries a `User-Agent` naming this repository.

The automated run happens monthly.

## If you find a vulnerability in this scanner

Report it privately using GitHub's "Report a vulnerability" button on the
Security tab rather than opening a public issue. This is a scanner that
other people may point at their own infrastructure, so a flaw that makes
it send something it should not is worth handling quietly first.

## If a scan of yours revealed something about your endpoint

If a scan incidentally reveals a serious vulnerability in a specific
target, we disclose it privately to the endpoint owner and do not publish
the detail. That is policy, not courtesy.
