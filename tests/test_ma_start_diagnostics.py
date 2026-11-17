"""A discovered identifier is not proof of the starting company's identity."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

from iterative_expansion import HelixFact
from run_company_ma_expansion import summarize_start_diagnostics


def test_seed_only_is_unresolved():
    seed = HelixFact(fact_type="COMPANY", value="Example", source="SEED")
    result = summarize_start_diagnostics([seed])
    assert result["start_status"] == "IDENTITY_UNRESOLVED"
    assert result["seed_only"] is True


def test_identifier_does_not_mean_verified_root():
    seed = HelixFact(fact_type="COMPANY", value="Example", source="SEED")
    unrelated = HelixFact(
        fact_type="LEGAL_ENTITY", value="Unrelated company",
        identifier="TEST-LEI", source="GLEIF_IDENTITY_FALLBACK",
    )
    result = summarize_start_diagnostics([seed, unrelated])
    assert result["start_status"] == "IDENTIFIER_CANDIDATES_FOUND"
    assert result["resolved_identifiers"] == 1
    assert "not been independently verified" in result["note"]


def test_unidentified_discoveries_remain_candidates():
    seed = HelixFact(fact_type="COMPANY", value="Example", source="SEED")
    other = HelixFact(fact_type="COMPANY", value="Possible alias", source="EDGAR")
    result = summarize_start_diagnostics([seed, other])
    assert result["start_status"] == "CANDIDATES_FOUND"
