import json

from a2a_scorecard.cli import main


def test_cli_json_output(fake_agent, capsys) -> None:
    url = fake_agent("compliant")
    exit_code = main(["scan", url, "--json", "--allow-http"])
    assert exit_code == 0
    reports = json.loads(capsys.readouterr().out)
    assert len(reports) == 1
    assert reports[0]["target"] == url
    assert reports[0]["grade"] == "A"


def test_cli_text_output(fake_agent, capsys) -> None:
    url = fake_agent("no-card")
    exit_code = main(["scan", url, "--allow-http"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "grade: F" in out
    assert "C010" in out
