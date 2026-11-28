"""Offline integration checks: actual production adapter, no paid or live API."""
from types import SimpleNamespace
from production_narration import rewrite_short, polish_long_opening, review_reference
from science_sources import Evidence

class Room:
    def __init__(self, output):
        self.output=output
        self.calls=[]
    def ask(self, role, prompt, schema, preferred, **kwargs):
        self.calls.append((role,kwargs))
        if role=="writer":
            return dict.fromkeys("abcde","A clock can run without electricity."),"writer"
        assert kwargs["avoid"]=="writer"
        return self.output,"editor"

def test_short_changes_only_narration(monkeypatch):
    monkeypatch.delenv('PURFFLE_SINGLE_PASS_NARRATION',raising=False)
    scenes=[SimpleNamespace(narration="A mechanical clock uses a spring.",object="clock",visual_search_query="clock mechanism"),
            SimpleNamespace(narration="The spring drives gears.",object="gears",visual_search_query="clock gears")]
    script=SimpleNamespace(scenes=scenes)
    texts=["A clock can run without electricity. Its spring stores energy when you wind it.",
           "As the spring unwinds, it turns a set of gears that control the steady movement of the clock hands around its face."]
    room=Room({"chosen":"a","scenes":texts})
    evidence=Evidence("Mechanical clocks",({"id":"1","title":"Reference","excerpt":"A clock can run without electricity. A wound spring stores energy and turns gears."},),"model_screened_reference")
    result,model=rewrite_short(script,"Mechanical clocks","en",evidence,room=room)
    assert result is script and model=="editor"
    assert [x.narration for x in result.scenes]==texts
    assert [x.visual_search_query for x in result.scenes]==["clock mechanism","clock gears"]
    assert len(room.calls)==2

def test_long_changes_first_chapter_only():
    text="A clock can run without electricity. Its spring stores energy when you wind it."
    chapters=[{"title":"The spring","narration":text,"visual_subject":"clock"},
              {"title":"The gears","narration":"The spring turns gears."}]
    room=Room({"chosen":"a","narration":text})
    result=polish_long_opening("Mechanical clocks","en",chapters,chapters,room=room,word_range=(10,30))
    assert result[0]["visual_subject"]=="clock" and result[1]==chapters[1]
    assert len(room.calls)==2

def test_curated_rewrites_do_not_use_exact_dossier_approval():
    bundle=Evidence("Why do octopuses have three hearts?",({"id":"official-1","title":"octopus","url":"https://ocean.si.edu/ocean-life/invertebrates/octopuses-squids-and-relatives","tier":"editor_reviewed_official_dossier"},),"curated_editor_reviewed")
    result=review_reference(bundle,bundle.topic,"en")
    assert result.method=="creative_dossier_reference"
    assert result.sources[0]["excerpt"]


def test_single_pass_never_overwrites_model_scenes(monkeypatch):
    monkeypatch.setenv("PURFFLE_SINGLE_PASS_NARRATION","1")
    scenes=[SimpleNamespace(narration="This wording stays.",object="clock"),
            SimpleNamespace(narration="Incorrect wording.",object="gears")]
    class Single:
        def ask(self,role,prompt,schema,preferred,**kwargs):
            assert role=="writer" and "This wording stays." in prompt
            return {"scenes":["Changed by the model.","A spring turns the gears."]},"writer"
    evidence=Evidence("Mechanical clocks",({"id":"1","title":"Clock","excerpt":"A spring turns the gears."},),"model_screened_reference")
    rewrite_short(SimpleNamespace(scenes=scenes),"Mechanical clocks","en",evidence,room=Single(),keep_indices=(0,))
    assert [x.narration for x in scenes]==["Changed by the model.","A spring turns the gears."]

def test_focused_passages_include_article_body():
    from narration_sources import passages
    unrelated="Aircraft have many different structures and use wings to generate lift. Their designs vary widely."
    relevant="Contrails form when water vapor in jet exhaust condenses into ice crystals in cold air at high altitude."
    result=passages(unrelated+"\n\n== Contrails ==\n"+relevant,"contrails","ice crystals jet exhaust","white trails")
    assert result[0][2]==relevant

def test_bilingual_review_anchor_not_literal_narration_word(monkeypatch):
    from science_sources import _validate_model_scene_checks
    monkeypatch.setenv("PURFFLE_SINGLE_PASS_NARRATION","1")
    excerpt="The light is emitted only in the presence of oxygen."
    evidence=Evidence("Light",({"id":"1","excerpt":excerpt},),"model_screened_reference")
    checks=[{"scene":1,"source_id":"1","quote":excerpt,"supported":True,"reason":"Translation."}]
    assert _validate_model_scene_checks(checks,[SimpleNamespace(narration="Das Licht entsteht nur in Gegenwart von Sauerstoff.")],evidence)[0]["supported"]
    checks[0]["quote"]="Invented quote that does not exist."
    assert not _validate_model_scene_checks(checks,[SimpleNamespace(narration="Das Licht entsteht nur in Gegenwart von Sauerstoff.")],evidence)[0]["supported"]

def test_material_review_distinguishes_facts_from_style(monkeypatch,tmp_path):
    from narration_review import review_short, WEIGHTS
    import science_sources
    from types import SimpleNamespace
    import json
    import pytest
    script=SimpleNamespace(scenes=[SimpleNamespace(narration="A spring stores energy."),SimpleNamespace(narration="It turns gears.")])
    evidence=Evidence("How does a clock work?",({"id":"ref-1","title":"Clock","excerpt":"A spring stores energy and drives gears."},),"model_screened_reference")
    verdict={"answers_question":True,"checks":[
        {"scene":1,"status":"supported","source_ids":["ref-1"],"reason":"Direct support"},
        {"scene":2,"status":"minor_issue","source_ids":["ref-1"],"reason":"Simplified wording"}],
        "scores":dict.fromkeys(WEIGHTS,4),"reason":"Plain delivery."}
    monkeypatch.setattr(science_sources,"_strict_science_review_json",lambda *args:verdict)
    path=tmp_path/"science.json"
    review_short(script,evidence,object(),path)
    report=json.loads(path.read_text())
    assert report["state"]=="model_screened_reference"
    assert report["topic_review"]["weighted_score"]==40
    assert report["scene_checks"][1]["supported"] is True
    verdict["checks"][1]["status"]="material_issue"
    with pytest.raises(RuntimeError,match="unsupported narration scene"):
        review_short(script,evidence,object(),path)
    verdict["checks"][1]["status"]="supported"
    verdict["checks"][1]["source_ids"]=["invented"]
    with pytest.raises(RuntimeError,match="science_review_unavailable"):
        review_short(script,evidence,object(),path)
    verdict["checks"][1]["source_ids"]=["ref-1"]
    verdict["answers_question"]=False
    with pytest.raises(RuntimeError,match="exact topic answer"):
        review_short(script,evidence,object(),path)


def test_single_pass_advisory_structure(monkeypatch):
    from retention_storyboard import audit_storyboard
    import pytest
    monkeypatch.setenv("PURFFLE_SINGLE_PASS_NARRATION","1")
    data=[{"narration":"A spring stores energy when wound."},{"narration":"It turns gears."}]
    assert audit_storyboard("How does a clock work?",None,scenes=data)["advisory_findings"]
    with pytest.raises(RuntimeError,match="repeated scene"):
        audit_storyboard("Clocks",None,scenes=[data[0],data[0]])
