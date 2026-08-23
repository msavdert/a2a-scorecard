"""Summarize a census run into the numbers that decide the project's future."""

from __future__ import annotations

import json
import sys
from collections import Counter


OK = {"pass", "warn"}


def reclassify(r: dict) -> str:
    """Recompute the outcome from stored raw check data, so the summary does not
    depend on whatever the collector labelled it at capture time."""
    if r.get("outcome") == "ERROR":
        return "ERROR"
    checks = {k: str(v).lower() for k, v in (r.get("checks") or {}).items()}
    if not checks:
        return "ERROR"
    if checks.get("C001") not in OK:
        return "UNREACHABLE"
    if checks.get("C010") in OK:
        return "SCANNABLE"
    card_ev = str((r.get("evidence") or {}).get("C010", "")).lower()
    if "401" in card_ev or "403" in card_ev or "auth" in card_ev:
        return "AUTH_GATED"
    return "REACHABLE_NO_CARD"


def main(path: str) -> int:
    records = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
    for r in records:
        r["outcome"] = reclassify(r)
    n = len(records)
    outcomes = Counter(r["outcome"] for r in records)
    scannable = [r for r in records if r["outcome"] == "SCANNABLE"]

    print(f"candidates probed:      {n}")
    print("outcomes:")
    for k, v in outcomes.most_common():
        print(f"  {k:<20} {v:>5}  ({v / n:.0%})")

    print(f"\nSCANNABLE population:   {len(scannable)}")
    if not scannable:
        return 0

    print("\ngrades (scannable only):")
    for g, v in sorted(Counter(r.get("grade") for r in scannable).items()):
        print(f"  {g:<3} {v:>5}  ({v / len(scannable):.0%})")

    print("\nspec generation:")
    for g, v in Counter(r.get("spec_generation") for r in scannable).most_common():
        print(f"  {str(g):<8} {v:>5}  ({v / len(scannable):.0%})")

    print("\ncoverage (applicable/max weight) - how much we could actually judge:")
    cov = Counter(
        f"{(r.get('coverage') or {}).get('applicable_weight')}/"
        f"{(r.get('coverage') or {}).get('max_weight')}"
        for r in scannable
    )
    for k, v in cov.most_common(8):
        print(f"  {k:<10} {v:>5}  ({v / len(scannable):.0%})")

    print("\nper-check status (scannable only):")
    check_ids = sorted({c for r in scannable for c in (r.get("checks") or {})})
    for cid in check_ids:
        c = Counter((r.get("checks") or {}).get(cid, "-") for r in scannable)
        parts = " ".join(f"{k}={v}" for k, v in c.most_common())
        print(f"  {cid}: {parts}")

    print("\nregistrable-domain concentration (top 10):")
    doms = Counter(".".join(r["host"].split(".")[-2:]) for r in records)
    for d, v in doms.most_common(10):
        print(f"  {d:<32} {v:>4}")
    hosts = {r["host"] for r in records}
    print(f"  distinct hosts={len(hosts)}  distinct domains={len(doms)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
