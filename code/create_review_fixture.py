#!/usr/bin/env python3
import argparse, json, os

def source_entity(name, jurisdiction, address):
    return {
        "provider": "fixture_registry",
        "provider_entity_id": None,
        "legal_name": name,
        "jurisdiction": jurisdiction,
        "registration_number": None,
        "status": None,
        "former_names": [],
        "addresses": [address],
        "attributes": {"fixture": True},
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--out",default="./data/processed/resolved_review_fixture.json")
    args=ap.parse_args()

    left={
        "node_id":"fixture:acme-llc",
        "canonical_name":"Acme Holdings LLC",
        "canonical_name_normalized":"acme holdings llc",
        "legal_name_base":"acme holdings",
        "jurisdiction":"US",
        "jurisdiction_raw":"US",
        "provider_entity_ids":[],
        "aliases":[],
        "roles":[],
        "source_entities":[
            source_entity(
                "Acme Holdings LLC","US",
                "100 Market Street, San Francisco, CA 94105"
            )
        ],
    }
    right={
        "node_id":"fixture:acme-inc",
        "canonical_name":"Acme Holdings Inc",
        "canonical_name_normalized":"acme holdings inc",
        "legal_name_base":"acme holdings",
        "jurisdiction":"US",
        "jurisdiction_raw":"US",
        "provider_entity_ids":[],
        "aliases":[],
        "roles":[],
        "source_entities":[
            source_entity(
                "Acme Holdings Inc","US",
                "100 Market Street, San Francisco, CA 94105"
            )
        ],
    }

    graph={
        "resolution_version":"m3.6-e2e-fixture-v1",
        "nodes":[left,right],
        "relationships":[],
        "resolution_events":[],
        "review_candidates":[{
            "left_node_id":left["node_id"],
            "right_node_id":right["node_id"],
            "reason":"same_legal_name_base_same_jurisdiction_no_identifier",
            "auto_merge":False,
        }],
        "warnings":[],
        "summary":{
            "node_count":2,
            "relationship_count":0,
            "merge_count":0,
            "review_candidate_count":1,
            "fixture":True,
            "expected_m35_decision":"REVIEW",
        },
    }

    os.makedirs(os.path.dirname(args.out) or ".",exist_ok=True)
    with open(args.out,"w",encoding="utf-8") as f:
        json.dump(graph,f,indent=2,ensure_ascii=False)
    print(f"Wrote REVIEW fixture -> {args.out}")

if __name__=="__main__":
    main()
