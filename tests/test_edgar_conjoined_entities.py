"""Regression for two legal entities joined by a conjunction."""
import importlib.util
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "code/parsers/edgar_ma_extractor.py"
spec = importlib.util.spec_from_file_location("edgar_ma_extractor_conjunction", MODULE)
extractor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extractor)


def test_two_legal_entities_are_not_merged():
    text = "Onum Technology Inc. and Pangea Cyber Corporation were acquired."
    names = [name for name, _ in extractor._entity_matches(text)]
    assert "Onum Technology Inc." in names
    assert "Pangea Cyber Corporation" in names
    assert "Onum Technology Inc. and Pangea Cyber Corporation" not in names


def test_legitimate_and_in_company_name_is_preserved():
    names = [name for name, _ in extractor._entity_matches("Johnson and Johnson Inc.")]
    assert "Johnson and Johnson Inc." in names


def test_alias_behavior_unchanged_for_single_entity():
    names = [name for name, _ in extractor._entity_matches('Onum Technology Inc. ("Onum")')]
    assert "Onum Technology Inc." in names


def test_split_entity_end_positions_and_alias_attribution():
    text = 'Onum Technology Inc. and Pangea Cyber Corporation ("Pangea") were acquired.'
    matches = dict(extractor._entity_matches(text))
    assert matches["Onum Technology Inc."] == text.index("Onum Technology Inc.") + len("Onum Technology Inc.")
    assert matches["Pangea Cyber Corporation"] == text.index("Pangea Cyber Corporation") + len("Pangea Cyber Corporation")
    assert matches["Onum Technology Inc."] < matches["Pangea Cyber Corporation"]
    assert extractor.RegexBackend().parse(text)["aliases"] == {"Pangea": "Pangea Cyber Corporation"}
