import copy
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from multi_shot_runtime import collect,validate_final_records
from multi_shot import digest

CONTRACT={"event_required":False,"index":1}
LICENSE={"id":"CC0-1.0","url":"https://creativecommons.org/publicdomain/zero/1.0/","source_page":"https://example.com/video"}

class Visuals:
    def __init__(self,tmp,fail=False):
        self.tmp=tmp
        self.fail=fail
        self.report={"scenes":[]}
        self.used=set()
        self.used_urls=set()
        self.used_hashes=set()
        self.credits=set()
        self._rejected_candidates={"long"}
        self.state_path=tmp/"ledger.json"
        self.matcher=None
        self.quality=SimpleNamespace(validate=lambda *a,**k:{"width":1080,"height":1920,"duration":9.1,"portrait_crop_scale":1.})
    def _save(self): pass
    def for_scene(self,idx,query,payload,topic,need,dest):
        n=len(self.used)+1
        if self.fail and n==2:
            raise RuntimeError("No suitable verified REAL VIDEO")
        path=self.tmp/f"{n}.mp4"
        path.write_bytes(str(n).encode())
        h=digest(path)
        match={"director_check":{"verified":True},"crop_focus_x":.5}
        row={"status":"selected","source":"example","id":str(n),"sha256":h,"original_sha256":h,
            "license":LICENSE,"director_contract":CONTRACT,"required_seconds":need,
            "plan":{"object":"water","action":"moving","visual_search_query":"water"},
            "match":match,"quality":{"portrait_crop_scale":1.}}
        self.report["scenes"].append(row)
        self.used.add(str(n));self.used_hashes.add(h);self.credits.add(str(n))
        self.state_path.write_text(json.dumps(sorted(self.used)))
        return SimpleNamespace(path=path,extra={"strict_validated":True,"match":match},source="example",id=str(n))

def assemble_stub(shots,counts,target,**kwargs):
    target.write_bytes(b"assembled")
    rows=[]
    cursor=0
    for r,n in zip(shots,counts):
        rows.append({**r,"frames":n,"start_frame":cursor,"post_crop_review":{"verified":True},"joined_review":{"verified":True}})
        cursor+=n
    return {"state":"verified_bundle","sha256":digest(target),"shots":rows,"frames":cursor,
            "duration":cursor/30,"output":{"fps":30,"frames":cursor}}

def run(v,tmp):
    return collect(v,0,"water",{"_visual_contract":CONTRACT},"water",9.,tmp,
        SimpleNamespace(width=1080,height=1920,fps=30),float("inf"),assembler=assemble_stub)

def test_three_shots_one_logical_scene(tmp_path):
    v=Visuals(tmp_path)
    item,row=run(v,tmp_path)
    assert len(v.report["scenes"])==1
    assert len(row["multi_shot"]["shots"])==3
    assert item.duration>=9.05
    assert len(v.credits)==3
    assert v._rejected_candidates=={"long"}
    validate_final_records([row])

def test_incomplete_bundle_rolls_back(tmp_path):
    v=Visuals(tmp_path,True)
    with pytest.raises(RuntimeError):
        run(v,tmp_path)
    assert not v.used and not v.credits and not v.state_path.exists()
    assert v.report["scenes"][0]["status"]=="discarded_partial_multishot"

def test_final_rejects_missing_review_and_reused_original(tmp_path):
    v=Visuals(tmp_path)
    _,row=run(v,tmp_path)
    bad=copy.deepcopy(row)
    bad["multi_shot"]["shots"][0]["joined_review"]["verified"]=False
    with pytest.raises(ValueError,match="output shot"):
        validate_final_records([bad])
    with pytest.raises(ValueError,match="duplicate"):
        validate_final_records([row,{"sha256":row["multi_shot"]["shots"][0]["original_sha256"]}])
