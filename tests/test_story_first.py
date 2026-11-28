from types import SimpleNamespace
import json
import pytest
import story_first
from science_sources import Evidence

def test_split_preserves_all_words():
    text="One real detail. Another sentence. A third. A fourth. A fifth. A sixth."
    chunks=story_first.split_story(text)
    assert 2<=len(chunks)<=4
    assert " ".join(chunks)==text

def test_planning_happens_after_review_and_keeps_exact_words(monkeypatch,tmp_path):
    monkeypatch.setenv("PURFFLE_SINGLE_PASS_NARRATION","1")
    monkeypatch.setenv("SCIENCE_REPORT",str(tmp_path/"science-report.json"))
    calls=[]
    raw="A wound spring stores energy. Its release turns gears and moves the hands. The clock keeps ticking without electricity."
    class Room:
        trace=[]
        def ask(self,role,prompt,schema,preferred,**kwargs):
            calls.append(role)
            if role=="editor_1":
                assert "A wound spring" in prompt
            return {"narration":raw},"test-"+role
    def review(candidate,bundle,llm,report):
        calls.append("review")
        assert " ".join(s.narration for s in candidate.scenes)==raw
    def planner(topic,language,segments,room):
        calls.append("plan")
        return SimpleNamespace(scenes=[SimpleNamespace(narration=x) for x in segments]),None,"test-planner"
    monkeypatch.setattr(story_first,"review_short",review)
    monkeypatch.setattr(story_first,"plan_story",planner)
    bundle=Evidence("Clock",({"id":"ref-1","title":"Clock","excerpt":raw},),"model_screened_reference")
    screenplay,_,_=story_first.produce_short_story("Clock","en",bundle,object(),tmp_path/"result.json",room=Room())
    assert calls==["writer","editor_1","review","plan"]
    output=json.loads((tmp_path/"narration.json").read_text())
    assert output["raw_narration"]==raw and output["scope"]=="accepted narration"
    assert " ".join(s.narration for s in screenplay.scenes)==raw

def test_failed_review_never_plans(monkeypatch,tmp_path):
    monkeypatch.setenv("PURFFLE_SINGLE_PASS_NARRATION","1")
    monkeypatch.setenv("SCIENCE_REPORT",str(tmp_path/"science-report.json"))
    raw="A wound spring stores energy. Its release turns gears and moves the hands."
    class Room:
        trace=[]
        def ask(self,*args,**kwargs):
            return {"narration":raw},"test-model"
    count=[]
    def reject(*args):
        count.append(1)
        raise RuntimeError("science_claim_unverified: unsupported narration scene")
    monkeypatch.setattr(story_first,"review_short",reject)
    monkeypatch.setattr(story_first,"plan_story",lambda *a:pytest.fail("rejected narration reached planner"))
    bundle=Evidence("Clock",({"id":"ref-1","title":"Clock","excerpt":raw},),"model_screened_reference")
    with pytest.raises(RuntimeError,match="unsupported narration"):
        story_first.produce_short_story("Clock","en",bundle,object(),tmp_path/"result.json",room=Room())
    assert len(count)==2

def test_plan_schema_cannot_return_narration():
    from jsonschema import Draft202012Validator
    props=story_first.PLAN_SCHEMA["properties"]["scenes"]["items"]
    assert "narration" not in props["properties"] and not props["additionalProperties"]

def test_conditional_editor_preserves_good_draft(monkeypatch,tmp_path):
    monkeypatch.setenv("PURFFLE_CONDITIONAL_EDIT","1")
    monkeypatch.setenv("PURFFLE_SINGLE_PASS_NARRATION","1")
    monkeypatch.setenv("SCIENCE_REPORT",str(tmp_path/"science-report.json"))
    calls=[]
    raw="A wound spring stores energy. Its release turns gears and moves the hands. The clock keeps ticking without electricity."
    class Room:
        trace=[]
        def ask(self,role,*args,**kwargs):
            calls.append(role)
            assert role=="writer"
            return {"narration":raw},"real-writer"
    monkeypatch.setattr(story_first,"review_short",lambda *args:calls.append("review"))
    monkeypatch.setattr(story_first,"plan_story",lambda topic,lang,segs,room:(SimpleNamespace(scenes=[SimpleNamespace(narration=s) for s in segs]),None,"planner"))
    bundle=Evidence("Clock",({"id":"ref-1","title":"Clock","excerpt":raw},),"model_screened_reference")
    script,_,writer=story_first.produce_short_story("Clock","en",bundle,object(),tmp_path/"result.json",room=Room())
    assert calls==["writer","review"] and writer=="real-writer"
    assert " ".join(s.narration for s in script.scenes)==raw

def test_integrity_rejects_wrong_language_and_cutoff():
    from narration_integrity import validate_text
    with pytest.raises(RuntimeError,match="wrong language"):
        validate_text("The tree grows in salty water because its roots filter the salt. This remarkable adaptation lets it survive where other trees cannot.","de")
    with pytest.raises(RuntimeError,match="unfinished"):
        validate_text("The rock slowly forms crystals deep underground and the water","en")
    assert validate_text("Die Wurzeln des Baumes halten einen großen Teil des Salzes zurück. Dadurch kann der Baum auch im salzigen Wasser wachsen.","de")["detected_language"]=="de"

@pytest.mark.parametrize("revised_score,revision_fails,expected",[(70,False,"original"),(82,False,"revised"),(0,True,"original")])
def test_qwen_optional_quality_edit_keeps_best_reviewed(monkeypatch,tmp_path,revised_score,revision_fails,expected):
    monkeypatch.setenv("PURFFLE_QWEN_PRIMARY","1")
    monkeypatch.setenv("PURFFLE_CONDITIONAL_EDIT","1")
    monkeypatch.setenv("PURFFLE_SINGLE_PASS_NARRATION","1")
    monkeypatch.setenv("SCIENCE_REPORT",str(tmp_path/"science-report.json"))
    original="A wound spring stores energy. Its release turns gears and moves the hands. The clock keeps ticking without electricity."
    revised="A mechanical clock can keep moving without electricity. Its wound spring releases energy through gears. The gears move the hands."
    calls=[]
    class Room:
        trace=[]
        def ask(self,role,prompt,schema,preferred,**kwargs):
            calls.append(role)
            if role=="writer":
                assert preferred[0]=="qwen/qwen3.8-27b"
                return {"narration":original},"qwen/qwen3.8-27b"
            assert role=="editor_1"
            return {"narration":revised},"gemini-3.1-flash-lite"
    def review(candidate,bundle,llm,report,**kwargs):
        text=" ".join(s.narration for s in candidate.scenes)
        assert kwargs.get("reviewer") is not None
        if text==revised and revision_fails:
            raise RuntimeError("science_claim_unverified: unsupported narration scene")
        score=72 if text==original else revised_score
        report.write_text(json.dumps({"topic_review":{"weighted_score":score,"scores":{"hook":5},"reason":"weak hook"}}))
    monkeypatch.setattr(story_first,"review_short",review)
    monkeypatch.setattr(story_first,"plan_story",lambda topic,lang,segs,room:(SimpleNamespace(scenes=[SimpleNamespace(narration=s) for s in segs]),None,"planner"))
    bundle=Evidence("Clock",({"id":"ref-1","title":"Clock","excerpt":original},),"model_screened_reference")
    screenplay,_,_=story_first.produce_short_story("Clock","en",bundle,object(),tmp_path/"result.json",room=Room())
    output=json.loads((tmp_path/"narration.json").read_text())
    assert output["raw_narration"]==(original if expected=="original" else revised)
    assert " ".join(s.narration for s in screenplay.scenes)==output["raw_narration"]
    report=json.loads((tmp_path/"science-report.json").read_text())
    assert report["topic_review"]["weighted_score"]==(72 if expected=="original" else revised_score)
    assert calls==["writer","editor_1"]
