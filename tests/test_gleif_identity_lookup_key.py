"""Regression coverage for punctuation-safe GLEIF identity lookup."""
import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

from identity_lookup import legal_name_lookup_key
from root_entity_resolver import find_seed_matches
from build_gleif_lei_index import configure_database, backfill_lookup_keys, create_indexes
from migrate_gleif_lookup_key import migrate


class IdentityLookupTests(unittest.TestCase):
    def test_punctuation_and_citrix(self):
        self.assertEqual(legal_name_lookup_key("CITRIX SYSTEMS, INC."), "citrix systems inc")
        self.assertEqual(legal_name_lookup_key("Citrix Systems Inc"), "citrix systems inc")

    def test_do_not_strip_meaningful_corporate_tokens(self):
        self.assertEqual(legal_name_lookup_key("SERVICE CORP INTERNATIONAL"), "service corp international")
        self.assertNotEqual(legal_name_lookup_key("SERVICE CORP INTERNATIONAL"),
                            legal_name_lookup_key("SERVICE INTERNATIONAL"))
        self.assertEqual(legal_name_lookup_key("INC Research Holdings, Inc."),
                         "inc research holdings inc")

    def test_legacy_database_migration_is_idempotent(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("""
            CREATE TABLE lei_entities (
                lei TEXT PRIMARY KEY,
                legal_name TEXT,
                legal_name_normalized TEXT,
                entity_status TEXT
            )
        """)
        conn.execute(
            "INSERT INTO lei_entities VALUES (?,?,?,?)",
            ("HCTKJGUQOPZ5NBK7NP58", "CITRIX SYSTEMS, INC.",
             "citrix systems, inc.", "ACTIVE"),
        )
        conn.commit()
        migrate(conn)
        migrate(conn)
        matches = find_seed_matches(conn, "Citrix Systems Inc")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["lei"], "HCTKJGUQOPZ5NBK7NP58")
        conn.close()

    def test_backfill_and_resolver(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        configure_database(conn)
        conn.execute(
            "INSERT INTO lei_entities(lei,legal_name,legal_name_normalized,entity_status) VALUES(?,?,?,?)",
            ("HCTKJGUQOPZ5NBK7NP58", "CITRIX SYSTEMS, INC.", "citrix systems, inc.", "ACTIVE"),
        )
        conn.commit()
        backfill_lookup_keys(conn)
        create_indexes(conn)
        found = find_seed_matches(conn, "Citrix Systems Inc")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["lei"], "HCTKJGUQOPZ5NBK7NP58")
        self.assertEqual(found[0]["legal_name_normalized"], "citrix systems, inc.")
        conn.close()


if __name__ == "__main__":
    unittest.main()
