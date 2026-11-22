#!/usr/bin/env python3
"""Small real ZIP fixtures for compact alias index + independent verifier."""
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from build_compact_gleif_alias_index import build
from verify_compact_gleif_alias_index import verify


class CompactAliasTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.dir = Path(self.temp.name)
        self.source = self.dir / "original.zip"
        self.target = self.dir / "compact.sqlite"
        self.records = [
            {"LEI": {"$": "FIRST"}, "Entity": {
                "LegalName": {"$": "Current Co"},
                "OtherEntityNames": {"OtherEntityName": [
                    {"$": "Old Co", "@type": "PREVIOUS_LEGAL_NAME"},
                    {"$": "Very Old Co", "@type": "PREVIOUS_LEGAL_NAME"},
                ]},
                "TransliteratedOtherEntityNames": {
                    "TransliteratedOtherEntityName": {"$": "Kurrent Co"}}}},
            {"LEI": {"$": "SECOND"}, "Entity": {"LegalName": {"$": "Just Current"}}},
            {"LEI": {"$": "THIRD"}, "Entity": {
                "OtherEntityNames": {"OtherEntityName":
                    {"$": "Old Third", "@type": "PREVIOUS_LEGAL_NAME"}}}},
        ]
        self.write_source()

    def tearDown(self):
        self.temp.cleanup()

    def write_source(self):
        with zipfile.ZipFile(self.source, "w") as z:
            z.writestr("original.json", json.dumps({"records": self.records}))

    def test_full_real_zip_all_aliases_and_provenance(self):
        result = build(self.source, self.target, progress_every=0)
        self.assertEqual(result["records_scanned"], 3)
        self.assertEqual(result["alias_entries"], 4)
        self.assertEqual(result["alias_bearing_entities"], 2)
        self.assertFalse(result["is_sample"])
        with sqlite3.connect(self.target) as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM source_observation").fetchone()[0], 2)
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM entity_name").fetchone()[0], 4)
            name_rows = db.execute(
                "SELECT name FROM entity_name ORDER BY name").fetchall()
            self.assertIn(("Very Old Co",), name_rows)
        verified = verify(self.source, self.target)
        self.assertEqual(verified["status"], "PASS")
        self.assertEqual(verified["aliases_verified"], 4)
        self.assertFalse(verified["is_sample"])

    def test_sample_marks_incomplete_and_still_verifies(self):
        result = build(self.source, self.target, max_records=2, progress_every=0)
        self.assertTrue(result["is_sample"])
        check = verify(self.source, self.target)
        self.assertTrue(check["is_sample"])
        self.assertEqual(check["records_verified"], 2)
        self.assertEqual(check["aliases_verified"], 3)

    def test_existing_database_never_replaced(self):
        self.target.write_bytes(b"sentinel")
        with self.assertRaises(FileExistsError):
            build(self.source, self.target)
        self.assertEqual(self.target.read_bytes(), b"sentinel")

    def test_tamper_is_detected(self):
        build(self.source, self.target, progress_every=0)
        with sqlite3.connect(self.target) as db:
            db.execute("UPDATE entity_name SET name='Corrupted' WHERE name='Old Co'")
        with self.assertRaisesRegex(ValueError, "Alias mismatch"):
            verify(self.source, self.target)

    def test_wrong_source_checksum_rejected(self):
        build(self.source, self.target, progress_every=0)
        self.records[0]["Entity"]["OtherEntityNames"]["OtherEntityName"][0]["$"] = "Tampered"
        self.write_source()
        with self.assertRaisesRegex(ValueError, "Archive checksum mismatch"):
            verify(self.source, self.target)


if __name__ == "__main__":
    unittest.main()
