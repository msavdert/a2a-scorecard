"""Run the census across the sample.

Concurrency is across operators, never within one: each worker owns a whole
operator group and walks it sequentially with a pause, so no host ever sees two
concurrent scans. That is what docs/SCANNING-POLICY.md requires of batch mode.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from a2a_scorecard.config import Settings
from a2a_scorecard.scan import run_scan

sys.path.insert(0, "/tmp/a2a-census")
from sample import operator_unit  # noqa: E402

WORKERS = 8
PAUSE_WITHIN_OPERATOR_S = 3.0
TIMEOUT_S = 8.0

_write_lock = threading.Lock()
_counter = {"done": 0}


def scan_one(url: str, settings: Settings) -> dict:
    record: dict = {"target": url, "operator": operator_unit(url)}
    t0 = time.monotonic()
    try:
        d = run_scan(url, settings).to_dict()
        record["grade"] = d.get("grade")
        record["score"] = d.get("score")
        record["spec_generation"] = d.get("spec_generation")
        record["coverage"] = {
            "applicable_weight": d.get("applicable_weight"),
            "max_weight": d.get("max_weight"),
        }
        record["checks"] = {r["check_id"]: r["status"] for r in d.get("results", [])}
        record["evidence"] = {
            r["check_id"]: str(r.get("evidence", ""))[:200]
            for r in d.get("results", [])
            if r["check_id"] in {"C001", "C010", "C012", "C020"}
        }
        record["outcome"] = "OK"
    except Exception as exc:  # noqa: BLE001 - one bad target must not stop the census
        record["outcome"] = "ERROR"
        record["error"] = f"{type(exc).__name__}: {exc}"[:300]
    record["elapsed_s"] = round(time.monotonic() - t0, 2)
    return record


def main(sample_path: str, out_path: str) -> int:
    urls = [
        line.strip().rstrip("/")
        for line in open(sample_path, encoding="utf-8")
        if line.strip() and not line.startswith("#")
    ]
    groups: dict[str, list[str]] = defaultdict(list)
    for u in urls:
        groups[operator_unit(u)].append(u)

    settings = Settings(timeout_s=TIMEOUT_S)
    total = len(urls)
    print(f"census: {total} targets across {len(groups)} operators, {WORKERS} workers",
          file=sys.stderr, flush=True)
    out = open(out_path, "w", encoding="utf-8")

    def do_group(members: list[str]) -> None:
        for i, url in enumerate(members):
            rec = scan_one(url, settings)
            with _write_lock:
                out.write(json.dumps(rec) + "\n")
                out.flush()
                _counter["done"] += 1
                n = _counter["done"]
            if n % 25 == 0:
                print(f"  ... {n}/{total}", file=sys.stderr, flush=True)
            if i + 1 < len(members):
                time.sleep(PAUSE_WITHIN_OPERATOR_S)

    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        list(pool.map(do_group, groups.values()))
    out.close()
    print(f"done in {round(time.monotonic() - started)}s -> {out_path}",
          file=sys.stderr, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
