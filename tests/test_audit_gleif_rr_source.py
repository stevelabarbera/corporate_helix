"""Source ZIP audit must stream raw GLEIF records and identify loss of periods."""
from pathlib import Path
import json
import sqlite3
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from audit_gleif_rr_source import inspect_source, compare_index


def test_raw_zip_audit_detects_duplicate_periods_without_modifying_files(tmp_path):
    child = "254900AVSAWDJLMUWV53"
    parent = "5493007JDSMX8Z5Z1902"

    def record(period):
        return {
            "RelationshipRecord": {
                "Relationship": {
                    "StartNode": {"NodeID": child},
                    "EndNode": {"NodeID": parent},
                    "RelationshipType": "IS_ULTIMATELY_CONSOLIDATED_BY",
                    "RelationshipStatus": "ACTIVE",
                    "RelationshipPeriods": {
                        "RelationshipPeriod": [
                            {"PeriodType": "RELATIONSHIP_PERIOD", "StartDate": "1970-03-31"},
                            {"PeriodType": "ACCOUNTING_PERIOD", "StartDate": period, "EndDate": period},
                        ]
                    },
                },
                "Registration": {
                    "RegistrationStatus": "PUBLISHED",
                    "LastUpdateDate": "2025-03-18",
                },
            }
        }
    wrappers = [record("2023-12-31"), record("2024-12-31")]
    raw = json.dumps({"RelationshipRecords": wrappers}, indent=2)
    zipped = tmp_path / "rr.zip"
    with zipfile.ZipFile(zipped, "w") as z:
        z.writestr("rr.json", raw)
    original = zipped.read_bytes()
    db = tmp_path / "rr.sqlite"
    with sqlite3.connect(db) as conn:
        conn.execute("""CREATE TABLE relationships (
            child_lei TEXT, parent_lei TEXT, relationship_type TEXT,
            relationship_status TEXT, relationship_start TEXT, relationship_end TEXT,
            accounting_start TEXT, accounting_end TEXT,
            registration_status TEXT, last_update_date TEXT
        )""")
        conn.execute(
            "INSERT INTO relationships VALUES (?, ?, ?, 'ACTIVE', '1970-03-31', NULL, ?, ?, 'PUBLISHED', '2025-03-18')",
            (child, parent, "IS_ULTIMATELY_CONSOLIDATED_BY", "2024-12-31", "2024-12-31"),
        )
    before_db = db.read_bytes()
    scanned = inspect_source(zipped, {child}, progress=0)
    assert scanned["records_scanned"] == 2
    assert len(scanned["matches"]) == 2
    assert scanned["duplicate_keys"][0]["raw_record_count"] == 2
    assert scanned["duplicate_keys"][0]["distinct_periods_and_updates"] == 2
    comparison = compare_index(db, scanned["matches"], {child})
    assert comparison["index_rows"] == 1
    assert comparison["rows"][0]["index_matches_complete_source_record"]
    assert comparison["rows"][0]["source_records_for_key"] == 2
    assert zipped.read_bytes() == original
    assert db.read_bytes() == before_db
