"""Draw a politeness-bounded, operator-stratified sample from the candidate list.

Two reasons not to scan all 2,479: every scan spends a benign SendMessage ping
that costs the target real compute, and the raw list is dominated by a handful
of operators running dozens of subdomains each. Capping per operator makes the
sample describe operators rather than subdomain sprawl.
"""

from __future__ import annotations

import random
import sys
from collections import OrderedDict, defaultdict
from urllib.parse import urlsplit

# Hosts under these suffixes are per-app tenants, so the full host - not the
# registrable domain - is the operator unit.
PAAS_SUFFIXES = (
    "vercel.app",
    "workers.dev",
    "onrender.com",
    "railway.app",
    "fly.dev",
    "run.app",
    "pages.dev",
    "herokuapp.com",
    "netlify.app",
    "deno.dev",
    "modal.run",
    "hf.space",
    "azurewebsites.net",
    "ngrok.io",
    "ngrok-free.app",
    "replit.dev",
    "koyeb.app",
    "cloudfunctions.net",
)

PER_OPERATOR_CAP = 2
SEED = 20260822


def operator_unit(url: str) -> str:
    host = urlsplit(url).netloc.lower().split(":")[0]
    for suf in PAAS_SUFFIXES:
        if host == suf or host.endswith("." + suf):
            return host
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def main(src: str, dest: str, target_n: int) -> int:
    urls = []
    seen = OrderedDict()
    with open(src, encoding="utf-8") as fh:
        for raw in fh:
            u = raw.strip().rstrip("/")
            if u and not u.startswith("#") and u not in seen:
                seen[u] = None
                urls.append(u)

    groups: dict[str, list[str]] = defaultdict(list)
    for u in urls:
        groups[operator_unit(u)].append(u)

    rng = random.Random(SEED)
    capped: list[str] = []
    for unit in sorted(groups):
        members = sorted(groups[unit])
        rng.shuffle(members)
        capped.extend(members[:PER_OPERATOR_CAP])

    rng.shuffle(capped)
    chosen = sorted(capped[:target_n])

    with open(dest, "w", encoding="utf-8") as out:
        out.write("\n".join(chosen) + "\n")

    print(f"input urls:        {len(urls)}")
    print(f"operator units:    {len(groups)}")
    print(f"after cap of {PER_OPERATOR_CAP}:   {len(capped)}")
    print(f"sampled:           {len(chosen)}  -> {dest}")
    print(f"operators sampled: {len({operator_unit(u) for u in chosen})}")
    big = sorted(groups.items(), key=lambda kv: -len(kv[1]))[:8]
    print("largest operators in raw list:")
    for unit, members in big:
        print(f"  {unit:<34} {len(members)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2], int(sys.argv[3])))
