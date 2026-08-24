#!/usr/bin/env python3
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from legal_nlp.transaction_interpreter import (
    agreement, completion, merger_actions, subsidiary_actions, conversion_actions
)

def emit(kind, filing, section, **kw):
    evidence = kw.pop("evidence", None)
    metadata = kw.pop("metadata", {})
    if evidence:
        metadata["evidence"] = evidence
    return {
        "event_type": kind,
        "event_date": filing["filing_date"],
        "confidence": "HIGH",
        "reason": "M3.8.3.2 legal-prose alias/role/action interpreter.",
        "sec_item": section["item"],
        "accession": filing["accession"],
        "source_url": filing["source_url"],
        "metadata": metadata,
        **kw
    }

def financing_only_item_101(section):
    if section["item"] != "1.01":
        return False
    q = section["text"].casefold()
    financing = any(x in q[:2200] for x in (
        "credit agreement", "senior notes", "underwriting agreement",
        "partial financing of the proposed acquisition", "term loan"
    ))
    actual_merger_execution = (
        "entered into an agreement and plan of merger" in q[:2200]
        or "entered into a merger agreement" in q[:2200]
    )
    return financing and not actual_merger_execution

def interpret(filing, section):
    text = section["text"]
    out = []

    if financing_only_item_101(section):
        return out

    if section["item"] == "1.01":
        x = agreement(text)
        if x:
            out.append(emit(
                "AGREED_TO_ACQUIRE", filing, section,
                acquirer=x["acquirer"], target=x["target"],
                subject=None, object_entity=None, result_entity=None,
                evidence=x["evidence"]
            ))

    elif section["item"] == "2.01":
        x = completion(text)
        target = x["target"] if x else None
        if x:
            out.append(emit(
                "ACQUIRED", filing, section,
                acquirer=x["acquirer"], target=x["target"],
                subject=None, object_entity=None, result_entity=None,
                evidence=x["evidence"]
            ))

        for y in merger_actions(text):
            out.append(emit(
                "MERGED_INTO", filing, section,
                acquirer=None, target=None,
                subject=y["subject"], object_entity=y["object_entity"],
                result_entity=y["result_entity"], evidence=y["evidence"]
            ))

        for y in conversion_actions(text, default_subject=target):
            out.append(emit(
                "CONVERTED_TO", filing, section,
                acquirer=None, target=None,
                subject=y["subject"], object_entity=None, result_entity=None,
                evidence=y["evidence"],
                metadata={
                    "from_legal_form": y["from_legal_form"],
                    "to_legal_form": y["to_legal_form"],
                    "result_name_explicitly_stated": False,
                    "do_not_infer_result_name": True
                }
            ))

        for y in subsidiary_actions(text):
            out.append(emit(
                "SUBSIDIARY_OF", filing, section,
                acquirer=None, target=None,
                subject=y["subject"], object_entity=y["object_entity"],
                result_entity=None, evidence=y["evidence"]
            ))

    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    raw = json.loads(Path(a.inp).read_text(encoding="utf-8"))
    total = 0
    for filing in raw.get("filings", []):
        new = []
        for section in filing.get("sections", []):
            new.extend(interpret(filing, section))
        filing["event_candidates"] = new
        total += len(new)
        print(f"{filing['filing_date']} -> {len(new)} event(s) {[e['event_type'] for e in new]}")

    raw["schema_version"] = "m3.8.3.2-edgar-events-raw-v1"
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(raw.get('filings', []))} filing(s), {total} event(s) -> {a.out}")

if __name__ == "__main__":
    main()
