"""Read-only raw GLEIF L2 evidence inspection regression."""
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from inspect_gleif_relationship import inspect


def test_inspect_preserves_l2_dates_and_source(tmp_path):
    db = tmp_path / "rr.sqlite"
    with sqlite3.connect(db) as conn:
        conn.executescript("""
            CREATE TABLE relationships (
                child_lei TEXT, parent_lei TEXT,
                relationship_type TEXT, relationship_status TEXT,
                relationship_start TEXT, relationship_end TEXT,
                accounting_start TEXT, accounting_end TEXT,
                registration_status TEXT, last_update_date TEXT,
                source_file TEXT
            );
            CREATE TABLE index_metadata (key TEXT PRIMARY KEY, value TEXT);
            INSERT INTO index_metadata VALUES ('source_file', 'rr.zip');
            INSERT INTO relationships VALUES (
                'CHILD', 'PARENT', 'IS_ULTIMATELY_CONSOLIDATED_BY',
                'ACTIVE', '2012-01-01', '2019-06-16',
                '2012-01-01', '2019-06-16', 'PUBLISHED',
                '2026-06-01', 'rr.zip'
            );
        """)
    before = db.read_bytes()
    report = inspect(db, "CHILD", "PARENT")
    assert report["expected_parent_present"] is True
    assert report["relationship_count"] == 1
    assert report["source_metadata"]["source_file"] == "rr.zip"
    assert report["relationships"][0]["relationship_end"] == "2019-06-16"
    assert report["database_modified"] is False
    assert db.read_bytes() == before
