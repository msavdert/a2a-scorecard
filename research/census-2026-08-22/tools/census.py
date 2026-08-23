"""Throwaway population census harness for a2a-scorecard.

Reads candidate base URLs, runs the real scanner sequentially (one host at a
time, with a pause between targets) and writes one JSON object per target.
Nothing here is part of the product; it exists to answer "how many public,
scannable A2A endpoints actually exist".
"""

from __future__ import annotations

import json
import sys
import time
from collections import OrderedDict
from urllib.parse import urlsplit

from a2a_scorecard.config import Settings
from a2a_scorecard.scan import run_scan

PAUSE_BETWEEN_TARGETS_S = 3.0


def load_candidates(path: str) -> list[str]:
    seen: OrderedDict[str, None] = OrderedDict()
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            seen.setdefault(line.rstrip("/"), None)
    return list(seen)


OK = {"pass", "warn"}


def classify(report_dict: dict) -> str:
    by_id = {r["check_id"]: r for r in report_dict.get("results", [])}
    c001 = str(by_id.get("C001", {}).get("status", "")).lower()
    c010 = by_id.get("C010", {})
    c010_status = str(c010.get("status", "")).lower()
    card_evidence = str(c010.get("evidence", "")).lower()

    if c001 not in OK:
        return "UNREACHABLE"
    if c010_status in OK:
        return "SCANNABLE"
    if "401" in card_evidence or "403" in card_evidence or "auth" in card_evidence:
        return "AUTH_GATED"
    return "REACHABLE_NO_CARD"


def main(candidates_path: str, out_path: str) -> int:
    candidates = load_candidates(candidates_path)
    # Group by host so we never hit the same host back-to-back.
    settings = Settings(timeout_s=10.0)
    print(f"census: {len(candidates)} candidates", file=sys.stderr)

    with open(out_path, "w", encoding="utf-8") as out:
        for i, url in enumerate(candidates, 1):
            host = urlsplit(url).netloc or url
            record: dict = {"target": url, "host": host}
            t0 = time.monotonic()
            try:
                report = run_scan(url, settings)
                d = report.to_dict()
                record["outcome"] = classify(d)
                record["grade"] = d.get("grade")
                record["score"] = d.get("score")
                record["spec_generation"] = d.get("spec_generation")
                record["coverage"] = {
                    "applicable_weight": d.get("applicable_weight"),
                    "max_weight": d.get("max_weight"),
                }
                record["checks"] = {
                    r["check_id"]: r["status"] for r in d.get("results", [])
                }
                record["evidence"] = {
                    r["check_id"]: r.get("evidence", "")[:200]
                    for r in d.get("results", [])
                    if r["check_id"] in {"C001", "C010"}
                }
            except Exception as exc:  # noqa: BLE001 - census must not abort
                record["outcome"] = "ERROR"
                record["error"] = f"{type(exc).__name__}: {exc}"[:300]
            record["elapsed_s"] = round(time.monotonic() - t0, 2)
            out.write(json.dumps(record) + "\n")
            out.flush()
            print(
                f"[{i}/{len(candidates)}] {record['outcome']:<18} "
                f"{record.get('grade') or '-':<3} {url}",
                file=sys.stderr,
            )
            if i < len(candidates):
                time.sleep(PAUSE_BETWEEN_TARGETS_S)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
