import json,importlib.util
from pathlib import Path
P=Path(__file__).resolve().parents[1]/"code/eval/run_ma_saturation.py"
s=importlib.util.spec_from_file_location("sat",P); m=importlib.util.module_from_spec(s); s.loader.exec_module(m)
def test_novelty_curve(tmp_path):
    study={"study_id":"x","companies":[{"order":1,"id":"a","company":"A"},{"order":2,"id":"b","company":"B"},{"order":3,"id":"c","company":"C"}]}
    vals=[("a",["P1"],["F1"]),("b",["P1","P2"],["F1"]),("c",["P1"],["F1"])]
    for cid,ps,fs in vals: (tmp_path/f"{cid}.json").write_text(json.dumps({"pipeline":{},"observed_primitives":ps,"failure_classes":fs}))
    r=m.summarize(study,tmp_path)
    assert [x["new_primitive_count"] for x in r["rows"]]==[1,1,0]
    assert [x["new_failure_class_count"] for x in r["rows"]]==[1,0,0]
    assert r["primitive_vocabulary_size"]==2 and r["failure_vocabulary_size"]==1
def test_missing_is_not_novelty(tmp_path):
    r=m.summarize({"study_id":"x","companies":[{"order":1,"id":"a","company":"A"}]},tmp_path)
    assert r["companies_completed"]==0 and r["primitive_vocabulary_size"]==0
