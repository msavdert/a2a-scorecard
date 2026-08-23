"""Tests for src/a2a_scorecard/targets.py (ADR-0019).

Pure-data tests: no network, no fake-agent fixture. Writes only to
tmp_path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from a2a_scorecard.targets import (
    Exclusion,
    Target,
    TargetListError,
    apply_exclusions,
    load_exclusions,
    load_targets,
    normalize_target,
    operator_unit,
)

# --- normalize_target ---------------------------------------------------


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://Agent.Example.com", "https://agent.example.com"),
        ("https://agent.example.com:443", "https://agent.example.com"),
        ("http://agent.example.com:80", "http://agent.example.com"),
        ("https://agent.example.com/", "https://agent.example.com"),
        ("https://agent.example.com/a2a/", "https://agent.example.com/a2a"),
        ("https://agent.example.com/a2a", "https://agent.example.com/a2a"),
        ("https://agent.example.com:8443", "https://agent.example.com:8443"),
    ],
)
def test_normalize_target(url: str, expected: str) -> None:
    assert normalize_target(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "https://Agent.Example.com",
        "https://agent.example.com:443",
        "https://agent.example.com/a2a/",
        "https://agent.example.com:8443/x/",
    ],
)
def test_normalize_target_is_idempotent(url: str) -> None:
    once = normalize_target(url)
    twice = normalize_target(once)
    assert once == twice


def test_normalize_target_preserves_non_default_port() -> None:
    assert normalize_target("https://example.com:8443") == "https://example.com:8443"


def test_normalize_target_drops_only_matching_default_port() -> None:
    # port 80 on https is not the default for that scheme, so it stays.
    assert normalize_target("https://example.com:80") == "https://example.com:80"


# --- operator_unit --------------------------------------------------------


def test_operator_unit_registrable_domain() -> None:
    assert operator_unit("https://agent.example.com") == "example.com"
    assert operator_unit("https://api.sub.example.co.uk") == "co.uk"


def test_operator_unit_paas_vercel() -> None:
    assert operator_unit("https://my-app.vercel.app") == "my-app.vercel.app"


def test_operator_unit_paas_workers_dev() -> None:
    assert operator_unit("https://worker123.workers.dev") == "worker123.workers.dev"


def test_operator_unit_paas_railway() -> None:
    assert operator_unit("https://foo-production.up.railway.app") == (
        "foo-production.up.railway.app"
    )


def test_operator_unit_distinct_tenants_under_same_paas_suffix() -> None:
    a = operator_unit("https://tenant-a.vercel.app")
    b = operator_unit("https://tenant-b.vercel.app")
    assert a != b


# --- load_targets: provenance hard-failure --------------------------------


def _write(path: Path, lines: list[str]) -> Path:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _valid_target_line(target: str = "https://agent.example.com") -> str:
    return (
        f'{{"target": "{target}", "operator": "example.com", '
        '"sources": [{"directory": "a2a-registry.org", '
        '"ref": "https://a2a-registry.org", "kind": "registry", '
        '"observed_at": "2026-08-20"}], '
        '"first_seen": "2026-08-20", "tags": ["t"], "notes": ""}'
    )


def test_load_targets_happy_path(tmp_path: Path) -> None:
    p = _write(tmp_path / "targets.jsonl", [_valid_target_line()])
    targets = load_targets(str(p))
    assert len(targets) == 1
    assert targets[0].target == "https://agent.example.com"
    assert targets[0].target_id == "https://agent.example.com"
    assert targets[0].sources[0].kind == "registry"


def test_load_targets_raises_on_missing_sources(tmp_path: Path) -> None:
    bad = (
        '{"target": "https://agent.example.com", "operator": "example.com", '
        '"first_seen": "2026-08-20"}'
    )
    p = _write(tmp_path / "targets.jsonl", [bad])
    with pytest.raises(TargetListError) as exc_info:
        load_targets(str(p))
    assert "targets.jsonl:1" in str(exc_info.value)


def test_load_targets_raises_on_empty_sources_list(tmp_path: Path) -> None:
    bad = (
        '{"target": "https://agent.example.com", "operator": "example.com", '
        '"sources": [], "first_seen": "2026-08-20"}'
    )
    p = _write(tmp_path / "targets.jsonl", [bad])
    with pytest.raises(TargetListError):
        load_targets(str(p))


def test_load_targets_error_names_offending_line(tmp_path: Path) -> None:
    bad = (
        '{"target": "https://agent.example.com", "operator": "example.com", '
        '"first_seen": "2026-08-20"}'
    )
    p = _write(
        tmp_path / "targets.jsonl",
        [
            "# a comment",
            "",
            _valid_target_line("https://ok.example.com"),
            bad,
        ],
    )
    with pytest.raises(TargetListError) as exc_info:
        load_targets(str(p))
    assert ":4:" in str(exc_info.value)


# --- load_targets: comments and blank lines --------------------------------


def test_load_targets_skips_blank_and_comment_lines(tmp_path: Path) -> None:
    p = _write(
        tmp_path / "targets.jsonl",
        [
            "# leading comment",
            "",
            _valid_target_line("https://a.example.com"),
            "   ",
            "# another comment",
            _valid_target_line("https://b.example.com"),
        ],
    )
    targets = load_targets(str(p))
    assert [t.target for t in targets] == [
        "https://a.example.com",
        "https://b.example.com",
    ]


# --- Exclusions -------------------------------------------------------------


def _make_target(url: str) -> Target:
    from a2a_scorecard.targets import Source

    return Target(
        target=url,
        operator=operator_unit(url),
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


def test_apply_exclusions_url_scope() -> None:
    kept_target = _make_target("https://agent.example.com/other")
    excluded_target = _make_target("https://agent.example.com")
    exclusion = Exclusion(pattern="https://agent.example.com", scope="url")
    kept, excluded = apply_exclusions([kept_target, excluded_target], [exclusion])
    assert kept == [kept_target]
    assert excluded == [excluded_target]


def test_apply_exclusions_host_scope() -> None:
    excluded_target = _make_target("https://agent.example.com")
    kept_target = _make_target("https://api.agent.example.com")
    exclusion = Exclusion(pattern="agent.example.com", scope="host")
    kept, excluded = apply_exclusions([kept_target, excluded_target], [exclusion])
    assert kept == [kept_target]
    assert excluded == [excluded_target]


def test_apply_exclusions_domain_scope_covers_subdomains() -> None:
    root = _make_target("https://example.com")
    sub = _make_target("https://api.example.com")
    exclusion = Exclusion(pattern="example.com", scope="domain")
    kept, excluded = apply_exclusions([root, sub], [exclusion])
    assert kept == []
    assert sorted(t.target for t in excluded) == sorted([root.target, sub.target])


def test_apply_exclusions_domain_scope_does_not_match_near_miss_host() -> None:
    innocent = _make_target("https://notexample.com")
    exclusion = Exclusion(pattern="example.com", scope="domain")
    kept, excluded = apply_exclusions([innocent], [exclusion])
    assert kept == [innocent]
    assert excluded == []


def test_load_exclusions_skips_comments_and_blanks(tmp_path: Path) -> None:
    p = _write(
        tmp_path / "exclusions.jsonl",
        [
            "# header comment",
            "",
            '{"pattern": "example.com", "scope": "domain", "reason": "owner request"}',
        ],
    )
    exclusions = load_exclusions(str(p))
    assert len(exclusions) == 1
    assert exclusions[0].pattern == "example.com"
    assert exclusions[0].scope == "domain"


def test_load_targets_applies_exclusions_when_path_given(tmp_path: Path) -> None:
    targets_path = _write(
        tmp_path / "targets.jsonl",
        [
            _valid_target_line("https://agent.example.com"),
            _valid_target_line("https://other.example.org"),
        ],
    )
    exclusions_path = _write(
        tmp_path / "exclusions.jsonl",
        ['{"pattern": "example.com", "scope": "domain"}'],
    )
    targets = load_targets(str(targets_path), str(exclusions_path))
    assert [t.target for t in targets] == ["https://other.example.org"]
