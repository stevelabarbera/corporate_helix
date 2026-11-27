"""Real-filing-excerpt regression guards for Monsanto's June 2018 closing."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

from parsers.edgar_ma_extractor import infer_events
from providers.edgar_resolver import select_ma_8k_sections


# Short excerpts from Monsanto's public June 2018 8-Ks, reproduced as
# regression fixtures. They are evidence excerpts, not fabricated acquisitions.
CLOSING_8_01 = (
    "Item 8.01 Other Events. On June 7, 2018, Monsanto Company "
    "(\u201cMonsanto\u201d) issued a press release announcing the completion "
    "of the merger of KWA Investment Co. (\u201cMerger Sub\u201d) with and into "
    "Monsanto, with Monsanto continuing as an indirect, wholly-owned "
    "subsidiary of Bayer Aktiengesellschaft, a German stock corporation "
    "(\u201cBayer\u201d), pursuant to the Agreement and Plan of Merger."
)
INTRO = (
    "Introductory Note On June 7, 2018 (the \u201cClosing Date\u201d), "
    "pursuant to the Agreement and Plan of Merger, dated as of "
    "September 14, 2016 (the \u201cMerger Agreement\u201d), "
    "by and among Bayer Aktiengesellschaft, a German stock corporation, "
    "and Monsanto Company, the merger was completed. "
)
CONTROL = (
    "Item 5.01 Changes in Control of Registrant. As a result of the Merger, "
    "a change in control of the Company occurred, and the Company is now "
    "a wholly owned subsidiary of Bayer."
)


class Closing8KRegressions(unittest.TestCase):
    def test_8_01_closing_is_selected(self):
        items = select_ma_8k_sections(CLOSING_8_01)
        self.assertEqual([s["item"] for s in items], ["8.01"])

    def test_introductory_note_and_change_in_control_selected(self):
        text = INTRO + "\n" + CONTROL + "\nItem 9.01 Financial Statements and Exhibits."
        selected = select_ma_8k_sections(text)
        self.assertEqual([s["item"] for s in selected], ["8K_INTRO_CLOSING", "5.01"])

    def test_routine_8_01_does_not_trigger_acquisition_selection(self):
        text = "Item 8.01 Other Events. The Company changed its headquarters."
        self.assertEqual(select_ma_8k_sections(text), [])

    def test_merger_agreement_is_not_closing(self):
        text = (
            "Item 8.01 Other Events. Monsanto Company entered into an "
            "agreement and plan of merger with Bayer Aktiengesellschaft. "
            "Completion remains subject to regulatory approval."
        )
        self.assertEqual(select_ma_8k_sections(text), [])

    def test_real_monsanto_closing_emits_correct_direction(self):
        aliases={"Monsanto": "Monsanto Company", "Bayer": "Bayer Aktiengesellschaft"}
        orgs=["Monsanto Company","Bayer Aktiengesellschaft","KWA Investment Co."]
        events=infer_events(CLOSING_8_01,aliases,orgs,"8.01")
        matches=[e for e in events if e["extraction_rule"] ==
                 "COMPLETED_MERGER_SURVIVING_SUBSIDIARY"]
        self.assertEqual(len(matches),1, events)
        self.assertEqual(
            (matches[0]["event_type"],matches[0]["subject"],
             matches[0]["object"],matches[0]["status"]),
            ("ACQUIRED","Bayer Aktiengesellschaft","Monsanto Company","COMPLETED"),
        )

    def test_ownership_alone_is_not_an_acquisition(self):
        aliases={"Monsanto":"Monsanto Company","Bayer":"Bayer Aktiengesellschaft"}
        events=infer_events(
            "Monsanto is now a wholly owned subsidiary of Bayer Aktiengesellschaft.",
            aliases, ["Monsanto Company","Bayer Aktiengesellschaft"], "5.01"
        )
        self.assertFalse(any(e["event_type"]=="ACQUIRED" for e in events))

    def test_future_merger_does_not_emit_completed_acquisition(self):
        aliases={"Monsanto":"Monsanto Company","Bayer":"Bayer Aktiengesellschaft"}
        future=CLOSING_8_01.replace("announcing the completion of the merger",
                                   "announcing a proposed merger")
        events=infer_events(
            future,aliases,["Monsanto Company","Bayer Aktiengesellschaft",
                            "KWA Investment Co."],"8.01"
        )
        self.assertFalse(any(e["event_type"]=="ACQUIRED" for e in events))


if __name__ == "__main__":
    unittest.main()
