"""Politeness-bounded, operator-stratified sampling.

Productised from research/census-2026-08-22/tools/sample.py per
ADR-0019. Two reasons not to scan every listed target: every scan spends
a benign SendMessage ping that costs the target real compute, and the
raw list is dominated by a handful of operators running dozens of
subdomains each. Capping per operator makes a sample describe operators
rather than subdomain sprawl.
"""

from __future__ import annotations

import random

from a2a_scorecard.targets import Target, operator_unit


def draw_sample(
    targets: list[Target],
    *,
    seed: int,
    per_operator_cap: int,
    n: int,
) -> list[Target]:
    """Draw a deterministic, operator-capped sample of up to `n` targets.

    Groups `targets` by `operator_unit`, shuffles each group and keeps at
    most `per_operator_cap` per operator, shuffles the survivors, then
    takes the first `n`. The result is sorted by `target_id` for a stable
    diff.

    Deterministic for a given `seed`: two calls with the same seed and
    inputs return the same targets in the same order (up to the final
    sort). Different seeds are expected to draw differently.
    """
    groups: dict[str, list[Target]] = {}
    for target in targets:
        groups.setdefault(operator_unit(target.target), []).append(target)

    rng = random.Random(seed)
    capped: list[Target] = []
    for unit in sorted(groups):
        members = sorted(groups[unit], key=lambda t: t.target_id)
        rng.shuffle(members)
        capped.extend(members[:per_operator_cap])

    rng.shuffle(capped)
    chosen = capped[:n]
    return sorted(chosen, key=lambda t: t.target_id)
