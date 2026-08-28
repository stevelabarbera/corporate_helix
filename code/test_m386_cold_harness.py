#!/usr/bin/env python3
import json
from pathlib import Path
m=json.loads(Path("./data/benchmark/disney_cold_manifest.json").read_text())
assert len(m["cases"])==4
assert len({x["accession"] for x in m["cases"]})==4
assert [x["item"] for x in m["cases"]]==["1.01","1.01","2.01","EXPLANATORY NOTE"]
print("PASS four-case cold manifest")
print("PASS unique accession pins")
print("PASS agreement/amendment/separation/closing coverage")
print("\n3 passed / 0 failed")
