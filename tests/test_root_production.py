import json
from types import SimpleNamespace
from unittest.mock import patch
import pytest

from retention_storyboard import validate_short_duration
from science_sources import _fallback_search_queries
from long_generic import _retried_json, build_multilingual_documentary
from youtube_metadata import attach_title_to_video

@pytest.mark.parametrize("seconds,target",[(8.1,16),(float("nan"),16),(20,40),(65,55)])
def test_unpublishable_short_duration(seconds,target):
    with pytest.raises(RuntimeError,match="short_duration_invalid"):
        validate_short_duration(seconds,target)

def test_valid_adaptive_duration():
    assert validate_short_duration(24,30)==24

def test_actual_failed_science_topics_have_search_alternatives():
    assert "shark" in _fallback_search_queries("Why do sharks keep swimming?","en")
    assert "lightning" in _fallback_search_queries("What if lightning strikes the ocean?","en")
    assert "Haie" in _fallback_search_queries("Warum schwimmen Haie?","de")

def test_retry_includes_previous_validation_error():
    prompts=[]
    def complete(client,prompt,schema,name,**kwargs):
        prompts.append(prompt)
        return {"answer":"" if len(prompts)==1 else "valid"}
    def validate(value):
        if not value["answer"]:
            raise ValueError("chapter word count too low")
        return value
    with patch("long_generic._completion",side_effect=complete):
        assert _retried_json(None,"Write chapters",{},"test",validate,sleep=lambda _:None)=={"answer":"valid"}
    assert "chapter word count too low" in prompts[1]

def test_recovery_does_not_reuse_offtopic_title(tmp_path):
    video=tmp_path/"video.mp4"
    video.write_bytes(b"mock already validated")
    title=tmp_path/"YouTube_Title.txt"
    title.write_text("When Self-Driving Cars Turn Against Us")
    result={"status":"ok","mp4":str(video),"topic":"What If Robots Became Self-Aware?","language":"en"}
    with patch("youtube_metadata.make_short_title",return_value="What If Robots Became Self-Aware?"):
        attach_title_to_video(result)
    assert "Robots" in title.read_text()

def test_failed_pair_repairs_individual_chapters(monkeypatch):
    monkeypatch.delenv("PURFFLE_SCRIPT_CHECKPOINT",raising=False)
    outline=[{"title":f"Distinct section {i+1}","visual_subject":"ocean",
              "visual_search_query":"ocean waves"} for i in range(14)]
    monkeypatch.setattr("long_generic.generate_outline",lambda *a,**k:outline)
    calls=[]
    def fake(client,prompt,schema,name,validator,**kwargs):
        calls.append(name)
        if name=="long_documentary_chapters":
            raise RuntimeError("long_documentary_chapters_unverified_after_3_attempts:word_count")
        text=" ".join(["Wasser"]*112)
        return validator({"chapters":[{"title":"Abschnitt","narration":text}]})
    monkeypatch.setattr("long_generic._retried_json",fake)
    data=build_multilingual_documentary("Warum bewegen sich die Wellen?","de",client=object(),sleep=lambda _:None)
    assert len(data)==14 and calls.count("long_documentary_single")==14
    assert data[-1]["title"]==outline[-1]["title"]


def test_generic_volcano_mechanism_routes_to_exact_official_dossier():
    from fact_checked_topics import verified_documentary_kind,ground_verified_documentary
    from science_sources import discover_evidence
    from retention_storyboard import audit_storyboard
    for topic,lang in [("Why Do Volcanoes Erupt?","en"),("Warum brechen Vulkane aus?","de")]:
        assert verified_documentary_kind(topic)=="volcano_eruption"
        assert discover_evidence(topic,lang).method=="curated_editor_reviewed"
        story=ground_verified_documentary({},topic,lang,scene_count=3)
        spoken=" ".join(s["narration"] for s in story["scenes"]).casefold()
        assert "magma" in spoken
        assert ("pressure" if lang=="en" else "druck") in spoken
        assert "dormant" not in spoken and "extinct" not in spoken
        assert audit_storyboard(topic,None,lang,scenes=story["scenes"])["state"]=="editorial_screen_passed"
    assert verified_documentary_kind("Why did Mount St Helens erupt in 1980?")!="volcano_eruption"
    assert verified_documentary_kind("Why do underwater volcanoes erupt?")!="volcano_eruption"

def test_factually_true_but_offtopic_narration_does_not_pass_editor():
    from types import SimpleNamespace
    from science_sources import review_topic_answer,Evidence
    story=SimpleNamespace(title="Why Do Volcanoes Erupt?",scenes=[
        SimpleNamespace(narration="A dormant volcano is not erupting now.")])
    bundle=Evidence("Why Do Volcanoes Erupt?",(),"model_screened_reference")
    with patch("science_sources._strict_science_review_json",return_value={
        "answers_question":False,"opening_specific":True,"payoff_complete":False,"reason":"Classification, not cause"}):
        with pytest.raises(RuntimeError,match="exact topic answer"):
            review_topic_answer(story,bundle,None)

def test_quiet_volcano_never_demands_active_lava():
    from visual_director import build_contract,metadata_allows,visual_scores
    scene={"narration":"A dormant volcano is not erupting now, but may erupt later.",
           "object":"volcano","action":"ambient","visual_search_query":"volcanic mountain"}
    contract=build_contract(scene,"What are dormant volcanoes?",1)
    assert contract["family"]=="quiet_volcanic_context"
    assert not metadata_allows(contract,"volcano erupting lava fountain")
    assert metadata_allows(contract,"quiet volcanic crater landscape")
    assert not visual_scores(contract,[[.3,.1],[.1,.3],[.3,.1]])["verified"]

def test_source_overlay_only_counts_confident_multiword_lines():
    from source_overlay import line_evidence
    header="block_num\tpar_num\tline_num\tconf\ttext\n"
    assert line_evidence(header+"1\t1\t1\t93\tVolcano\n1\t1\t1\t92\teruption\n1\t1\t1\t96\ttoday\n")==[3]
    assert line_evidence(header+"1\t1\t1\t93\tVolcano\n1\t1\t1\t12\teruption\n1\t1\t2\t96\ttoday\n")==[]

def test_source_overlay_rejects_multiple_text_frames(monkeypatch):
    from source_overlay import check_source
    monkeypatch.setenv("PURFFLE_SOURCE_TEXT_GATE","1")
    with patch("source_overlay._read_frame",return_value=b"png"),patch("source_overlay._text",side_effect=[[4],[],[3]]):
        with pytest.raises(ValueError,match="source_overlay_text_detected"):
            check_source("unused",6)
    with patch("source_overlay._read_frame",return_value=b"png"),patch("source_overlay._text",side_effect=[[],[],[]]):
        assert check_source("unused",6)["state"]=="screened"
