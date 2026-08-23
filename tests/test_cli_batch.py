"""End-to-end tests for the `batch`, `report`, `preflight`, and
`scan --exclusions` CLI paths (the newly wired `cli.py`).

Tests never touch the network (CLAUDE.md rule 2). `batch` and `preflight`
both make a real HTTP request to the User-Agent's advertised contact URL
by design (ADR-0022); `check_contact_reachable` is exercised for real
against the in-process fake agent in `test_check_contact_reachable_*`
below, and is monkeypatched to a network-free stub everywhere else so
that driving `batch` through the CLI cannot reach the real internet.
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import pytest

from a2a_scorecard import dataset, preflight
from a2a_scorecard.cli import main
from a2a_scorecard.targets import normalize_target


def _write_targets(path: Path, urls: list[str]) -> None:
    lines = [
        json.dumps(
            {
                "target": url,
                "operator": f"operator-{i}.example",
                "sources": [
                    {
                        "directory": "test",
                        "ref": "test",
                        "kind": "registry",
                        "observed_at": "2026-08-22",
                    }
                ],
                "first_seen": "2026-08-22",
            }
        )
        for i, url in enumerate(urls)
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_exclusions(path: Path, exclusions: list[dict[str, str]]) -> None:
    lines = [json.dumps(e) for e in exclusions]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


@pytest.fixture
def stub_preflight_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stand in for `check_contact_reachable` so driving `batch` through the
    CLI never issues the real preflight GET to the real internet. The
    preflight logic itself is covered separately, for real, against the
    fake agent in the `test_check_contact_reachable_*` tests below."""
    monkeypatch.setattr(
        preflight, "check_contact_reachable", lambda *a, **kw: "http://stub.invalid/"
    )


# --- preflight, the real function against the fake agent -------------------


def test_check_contact_reachable_success(fake_agent) -> None:
    url = fake_agent("compliant")
    user_agent = f"a2a-scorecard/0.0.0-test (conformance scanner; {url}/)"
    with httpx.Client() as client:
        result = preflight.check_contact_reachable(user_agent=user_agent, client=client)
    assert result == f"{url}/"


def test_check_contact_reachable_404(fake_agent) -> None:
    url = fake_agent("no-card")
    contact = f"{url}/.well-known/agent-card.json"
    user_agent = f"a2a-scorecard/0.0.0-test (conformance scanner; {contact})"
    with httpx.Client() as client, pytest.raises(preflight.PreflightFailed, match="404"):
        preflight.check_contact_reachable(user_agent=user_agent, client=client)


def test_check_contact_reachable_no_url_in_user_agent() -> None:
    with pytest.raises(preflight.PreflightFailed, match="no contact URL"):
        preflight.check_contact_reachable(user_agent="a2a-scorecard/0.0.0-test (no url here)")


# --- batch, end-to-end -------------------------------------------------------


def test_batch_end_to_end(tmp_path: Path, fake_agent, stub_preflight_ok) -> None:
    urls = [fake_agent("compliant", host=h) for h in ("127.0.0.1", "127.0.0.2", "127.0.0.3")]
    targets_path = tmp_path / "targets.jsonl"
    exclusions_path = tmp_path / "exclusions.jsonl"
    _write_targets(targets_path, urls)
    _write_exclusions(exclusions_path, [])
    out_dir = tmp_path / "data" / "runs"

    exit_code = main(
        [
            "batch",
            "--targets",
            str(targets_path),
            "--exclusions",
            str(exclusions_path),
            "--out",
            str(out_dir),
            "--workers",
            "2",
        ]
    )
    assert exit_code == 0

    run_files = sorted(out_dir.glob("run-*.jsonl"))
    assert len(run_files) == 1
    run = dataset.read_run(run_files[0])
    assert run.header is not None
    assert run.complete
    assert len(run.targets) == 3
    for row in run.targets:
        assert row["scanner_version"]
        assert row["grading_version"]
        assert row["spec_version"]
        assert row["grading_manifest_digest"]

    index_path = out_dir.parent / "index.json"
    assert index_path.exists()
    last_scanned = json.loads(index_path.read_text())["last_scanned_at"]
    for url in urls:
        assert normalize_target(url) in last_scanned


def test_batch_removes_a_run_file_that_recorded_nothing(
    tmp_path: Path, fake_agent, stub_preflight_ok
) -> None:
    """ADR-0024: a run whose targets were all skipped leaves no file.

    A header and a footer wrapped around zero target records is not a
    record of anything, and the workflow would otherwise commit one on
    every same-day re-dispatch.
    """
    url = fake_agent("compliant")
    targets_path = tmp_path / "targets.jsonl"
    exclusions_path = tmp_path / "exclusions.jsonl"
    _write_targets(targets_path, [url])
    _write_exclusions(exclusions_path, [])
    out_dir = tmp_path / "data" / "runs"

    assert (
        main(
            [
                "batch",
                "--targets",
                str(targets_path),
                "--exclusions",
                str(exclusions_path),
                "--out",
                str(out_dir),
                "--workers",
                "1",
            ]
        )
        == 0
    )
    first = sorted(out_dir.glob("run-*.jsonl"))
    assert len(first) == 1

    # Second run inside the re-scan floor: everything is skipped_recent, so
    # nothing is written and the file must not survive.
    assert (
        main(
            [
                "batch",
                "--targets",
                str(targets_path),
                "--exclusions",
                str(exclusions_path),
                "--out",
                str(out_dir),
                "--workers",
                "1",
            ]
        )
        == 0
    )
    assert sorted(out_dir.glob("run-*.jsonl")) == first
    assert fake_agent.journal(url) != []


def test_batch_honours_rescan_floor(tmp_path: Path, fake_agent, stub_preflight_ok) -> None:
    urls = [fake_agent("compliant", host=h) for h in ("127.0.0.1", "127.0.0.2", "127.0.0.3")]
    targets_path = tmp_path / "targets.jsonl"
    exclusions_path = tmp_path / "exclusions.jsonl"
    _write_targets(targets_path, urls)
    _write_exclusions(exclusions_path, [])
    out_dir = tmp_path / "data" / "runs"
    args = [
        "batch",
        "--targets",
        str(targets_path),
        "--exclusions",
        str(exclusions_path),
        "--out",
        str(out_dir),
        "--workers",
        "2",
    ]

    assert main(args) == 0
    journal_lengths_before = {url: len(fake_agent.journal(url)) for url in urls}

    assert main(args) == 0

    # The floor held: no target was contacted a second time.
    for url in urls:
        assert len(fake_agent.journal(url)) == journal_lengths_before[url]

    # And per ADR-0024 the second run left nothing behind. skipped_recent is
    # a fact about our scheduler's clock, not about the target, so it is
    # counted and not written - and a run with no target records does not
    # keep its file.
    run_files = sorted(out_dir.glob("run-*.jsonl"))
    assert len(run_files) == 1
    first_run = dataset.read_run(run_files[0])
    assert {row["target_id"] for row in first_run.targets} == {
        normalize_target(url) for url in urls
    }
    assert all(row["outcome"] == "ok" for row in first_run.targets)


def test_batch_refuses_when_preflight_fails(
    tmp_path: Path, fake_agent, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    def fail(*args: object, **kwargs: object) -> str:
        raise preflight.PreflightFailed("contact URL https://example.invalid/ returned HTTP 404")

    monkeypatch.setattr(preflight, "check_contact_reachable", fail)

    url = fake_agent("compliant")
    targets_path = tmp_path / "targets.jsonl"
    exclusions_path = tmp_path / "exclusions.jsonl"
    _write_targets(targets_path, [url])
    _write_exclusions(exclusions_path, [])
    out_dir = tmp_path / "data" / "runs"

    exit_code = main(
        [
            "batch",
            "--targets",
            str(targets_path),
            "--exclusions",
            str(exclusions_path),
            "--out",
            str(out_dir),
        ]
    )

    assert exit_code == 2
    assert "preflight failed" in capsys.readouterr().err
    # The whole point: nothing gets scanned when the preflight fails.
    assert fake_agent.journal(url) == []
    assert not list(out_dir.glob("run-*.jsonl"))


def test_batch_applies_exclusions(tmp_path: Path, fake_agent, stub_preflight_ok, capsys) -> None:
    urls = [fake_agent("compliant", host=h) for h in ("127.0.0.1", "127.0.0.2", "127.0.0.3")]
    excluded_url = urls[1]
    excluded_host = urlsplit(excluded_url).hostname
    assert excluded_host is not None

    targets_path = tmp_path / "targets.jsonl"
    exclusions_path = tmp_path / "exclusions.jsonl"
    _write_targets(targets_path, urls)
    _write_exclusions(
        exclusions_path,
        [{"pattern": excluded_host, "scope": "domain", "reason": "test opt-out"}],
    )
    out_dir = tmp_path / "data" / "runs"

    exit_code = main(
        [
            "batch",
            "--targets",
            str(targets_path),
            "--exclusions",
            str(exclusions_path),
            "--out",
            str(out_dir),
            "--workers",
            "2",
        ]
    )
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "3 submitted" in out
    assert "excluded" in out
    assert fake_agent.journal(excluded_url) == []

    # Regression coverage for the cli.py fix (ADR-0019/0020): before it,
    # cli.py filtered exclusions itself and passed the already-filtered
    # target list to run_batch with BatchConfig.exclusions left empty, so
    # run_batch's own `excluded` outcome emission never fired - the target
    # was correctly not scanned, but no `excluded` row was written to the
    # dataset, leaving the opt-out with no audit trail. The fix passes ALL
    # targets plus BatchConfig(exclusions=...) so run_batch records the
    # exclusion itself.
    run_files = sorted(out_dir.glob("run-*.jsonl"))
    assert len(run_files) == 1
    run = dataset.read_run(run_files[0])
    excluded_target_id = normalize_target(excluded_url)
    rows_by_target = {row["target_id"]: row for row in run.targets}
    assert excluded_target_id in rows_by_target
    excluded_row = rows_by_target[excluded_target_id]
    assert excluded_row["outcome"] == "excluded"
    assert excluded_row["report"] is None

    # The excluded target still appears in the report's excluded/absence
    # bucket, not silently dropped and not counted as a failure.
    ok_target_ids = {
        row["target_id"] for row in run.targets if row["target_id"] != excluded_target_id
    }
    assert len(ok_target_ids) == 2
    outcomes_by_target = {row["target_id"]: row["outcome"] for row in run.targets}
    assert outcomes_by_target[excluded_target_id] == "excluded"
    assert all(outcomes_by_target[tid] == "ok" for tid in ok_target_ids)

    # And the excluded target shows up in the generated report's excluded
    # bucket, counted as an absence rather than omitted or counted as a
    # failure.
    report_path = tmp_path / "ECOSYSTEM.md"
    assert main(["report", "--runs", str(out_dir), "--out", str(report_path)]) == 0
    report_text = report_path.read_text(encoding="utf-8")
    assert "`excluded`: 1/3" in report_text


def test_scan_refuses_excluded_url(tmp_path: Path, fake_agent, capsys) -> None:
    url = fake_agent("compliant")
    host = urlsplit(url).hostname
    assert host is not None
    exclusions_path = tmp_path / "exclusions.jsonl"
    _write_exclusions(
        exclusions_path, [{"pattern": host, "scope": "host", "reason": "test opt-out"}]
    )

    exit_code = main(["scan", url, "--exclusions", str(exclusions_path), "--allow-http"])

    assert exit_code == 2
    err = capsys.readouterr().err
    assert str(exclusions_path) in err
    assert fake_agent.journal(url) == []


def test_report_end_to_end(tmp_path: Path, fake_agent, stub_preflight_ok) -> None:
    urls = [fake_agent("compliant", host=h) for h in ("127.0.0.1", "127.0.0.2", "127.0.0.3")]
    targets_path = tmp_path / "targets.jsonl"
    exclusions_path = tmp_path / "exclusions.jsonl"
    _write_targets(targets_path, urls)
    _write_exclusions(exclusions_path, [])
    out_dir = tmp_path / "data" / "runs"
    assert (
        main(
            [
                "batch",
                "--targets",
                str(targets_path),
                "--exclusions",
                str(exclusions_path),
                "--out",
                str(out_dir),
                "--workers",
                "2",
            ]
        )
        == 0
    )

    report_path = tmp_path / "ECOSYSTEM.md"
    exit_code = main(["report", "--runs", str(out_dir), "--out", str(report_path)])

    assert exit_code == 0
    text = report_path.read_text(encoding="utf-8")
    assert text.strip() != ""
    for url in urls:
        assert url not in text
        host = urlsplit(url).hostname
        assert host is not None
        assert host not in text


def test_report_empty_runs_dir_fails(tmp_path: Path) -> None:
    empty_runs = tmp_path / "runs"
    empty_runs.mkdir()
    report_path = tmp_path / "ECOSYSTEM.md"

    exit_code = main(["report", "--runs", str(empty_runs), "--out", str(report_path)])

    assert exit_code != 0
    assert not report_path.exists()


def test_batch_resume_latest_appends_to_same_file(
    tmp_path: Path, fake_agent, stub_preflight_ok
) -> None:
    urls = [fake_agent("compliant", host=h) for h in ("127.0.0.1", "127.0.0.2", "127.0.0.3")]
    targets_path = tmp_path / "targets.jsonl"
    exclusions_path = tmp_path / "exclusions.jsonl"
    _write_targets(targets_path, urls)
    _write_exclusions(exclusions_path, [])
    out_dir = tmp_path / "data" / "runs"
    args = [
        "batch",
        "--targets",
        str(targets_path),
        "--exclusions",
        str(exclusions_path),
        "--out",
        str(out_dir),
        "--workers",
        "2",
    ]

    assert main(args) == 0
    run_files = sorted(out_dir.glob("run-*.jsonl"))
    assert len(run_files) == 1
    run_path = run_files[0]
    journal_lengths_before = {url: len(fake_agent.journal(url)) for url in urls}

    # Simulate a killed run: drop the run_end footer line.
    lines = run_path.read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[-1])["record_type"] == "run_end"
    run_path.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
    assert not dataset.read_run(run_path).complete

    assert main([*args, "--resume-latest"]) == 0

    run_files_after = sorted(out_dir.glob("run-*.jsonl"))
    assert len(run_files_after) == 1
    assert run_files_after[0] == run_path
    resumed = dataset.read_run(run_path)
    assert resumed.complete
    for url in urls:
        assert len(fake_agent.journal(url)) == journal_lengths_before[url]
