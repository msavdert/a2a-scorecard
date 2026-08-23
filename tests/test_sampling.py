"""Tests for src/a2a_scorecard/sampling.py (ADR-0019).

Pure-data tests: no network, no fake-agent fixture.
"""

from __future__ import annotations

from a2a_scorecard.sampling import draw_sample
from a2a_scorecard.targets import Source, Target


def _target(url: str) -> Target:
    return Target(
        target=url,
        operator="",
        sources=[
            Source(
                directory="a2a-registry.org",
                ref="https://a2a-registry.org",
                kind="registry",
                observed_at="2026-08-20",
            )
        ],
        first_seen="2026-08-20",
    )


def _many_operator_targets() -> list[Target]:
    targets = []
    # Six operators (distinct registrable domains) each running many
    # subdomains (sprawl), plus some single-target operators, so the cap
    # actually has something to do.
    for op in range(6):
        for i in range(10):
            targets.append(_target(f"https://host{i}.operator{op}.example.com"))
    for i in range(20):
        targets.append(_target(f"https://solo{i}.example{i}.org"))
    return targets


def test_draw_sample_respects_per_operator_cap() -> None:
    targets = _many_operator_targets()
    sample = draw_sample(targets, seed=1, per_operator_cap=2, n=1000)
    from collections import Counter

    from a2a_scorecard.targets import operator_unit

    counts = Counter(operator_unit(t.target) for t in sample)
    assert all(c <= 2 for c in counts.values())


def test_draw_sample_respects_n() -> None:
    targets = _many_operator_targets()
    sample = draw_sample(targets, seed=1, per_operator_cap=2, n=5)
    assert len(sample) == 5


def test_draw_sample_is_sorted_by_target_id() -> None:
    targets = _many_operator_targets()
    sample = draw_sample(targets, seed=1, per_operator_cap=2, n=10)
    ids = [t.target_id for t in sample]
    assert ids == sorted(ids)


def test_draw_sample_deterministic_for_same_seed() -> None:
    targets = _many_operator_targets()
    first = draw_sample(targets, seed=42, per_operator_cap=2, n=10)
    second = draw_sample(targets, seed=42, per_operator_cap=2, n=10)
    assert [t.target for t in first] == [t.target for t in second]


def test_draw_sample_differs_across_seeds() -> None:
    targets = _many_operator_targets()
    a = draw_sample(targets, seed=1, per_operator_cap=2, n=10)
    b = draw_sample(targets, seed=2, per_operator_cap=2, n=10)
    assert [t.target for t in a] != [t.target for t in b]
