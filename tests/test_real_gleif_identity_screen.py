"""Smoke test the real-data runner with a synthetic legacy L1 database."""
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from build_gleif_lei_index import SCHEMA
from screen_gleif_real_identity import screen


def test_screen_legacy_l1_without_mutating_sources(tmp_path):
    lei, rr = tmp_path / "legacy_lei.sqlite", tmp_path / "rr.sqlite"
    with sqlite3.connect(lei) as conn:
        conn.executescript(SCHEMA.replace("    legal_name_lookup_key TEXT,\n", ""))
        conn.execute(
            "INSERT INTO lei_entities(lei, legal_name, legal_name_normalized, entity_status)"
            " VALUES (?, ?, ?, ?)",
            ("KNOWN", "Citrix Systems Inc", "citrix systems inc", "ACTIVE"),
        )
    with sqlite3.connect(rr) as conn:
        conn.execute(
            "CREATE TABLE relationships (child_lei TEXT, parent_lei TEXT,"
            " relationship_type TEXT, relationship_status TEXT)"
        )
        conn.commit()

    cohort = tmp_path / "cohort.json"
    cohort.write_text(json.dumps({
        "cases": [{"input": {"company_name": "Citrix Systems Inc"}}]
    }))
    output = tmp_path / "report.json"
    assert screen(lei, rr, cohort, output) == 0
    report = json.loads(output.read_text())
    assert report["l1_rows"] == 1
    assert report["data_kind"] == "UNADJUDICATED_SCREEN_NOT_ACCURACY"
    assert report["verified_identity_accuracy"] is None
    assert report["cases"] >= 1
    assert any(x["company"] == "Citrix Systems Inc" for x in report["results"])
    with sqlite3.connect(lei) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(lei_entities)")}
        assert "legal_name_lookup_key" not in columns
    with sqlite3.connect(rr) as conn:
        assert conn.execute("SELECT count(*) FROM relationships").fetchone()[0] == 0
