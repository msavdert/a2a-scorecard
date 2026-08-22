import json
from pathlib import Path

from a2a_scorecard.schema import validate_agent_card

FIXTURES = Path(__file__).parent / "fixtures"


def load_valid_card() -> dict:
    return json.loads((FIXTURES / "agent-card-valid.json").read_text())


def test_valid_card_has_no_errors() -> None:
    assert validate_agent_card(load_valid_card()) == []


def test_wrong_type_is_rejected() -> None:
    card = load_valid_card()
    card["skills"] = "oops"
    errors = validate_agent_card(card)
    assert errors
    assert any("skills" in e for e in errors)


def test_unknown_property_is_rejected() -> None:
    card = load_valid_card()
    card["definitelyNotInTheSpec"] = True
    errors = validate_agent_card(card)
    assert errors


def test_nested_reference_is_resolved() -> None:
    card = load_valid_card()
    card["supportedInterfaces"] = [{"url": 123}]
    errors = validate_agent_card(card)
    assert any("url" in e for e in errors)
