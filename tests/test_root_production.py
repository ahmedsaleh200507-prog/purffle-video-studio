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
        "answers_question":False,"opening_specific":True,"payoff_complete":False,"early_value":True,"coherent_progression":False,"natural_spoken_language":True,"sustained_specific_interest":False,"reason":"Classification, not cause"}):
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


def test_shared_editorial_rejects_short_and_nonadjacent_repeat(monkeypatch):
    from editorial_standard import audit_structure
    with pytest.raises(RuntimeError,match="under_32"):
        audit_structure(["The sky glows.","Light comes from gases."],"en",mode="short")
    repeated="The magnetic field guides energetic electrons toward the polar atmosphere."
    with pytest.raises(RuntimeError,match="repeated_sentence"):
        audit_structure([repeated,"Gases absorb energy and release it as visible light in the sky.",repeated],"en",mode="short")
    with pytest.raises(RuntimeError,match="generic_opening"):
        audit_structure(["Hallo zusammen, heute sehen wir die Natur."],"de",mode="long")

def test_long_chapter_context_preserves_entire_arc():
    from editorial_standard import chapter_context,chapter_phase
    outline=[{"title":f"Section {i}"} for i in range(1,15)]
    context=chapter_context(outline,8,"The previous chapter explains the real physical mechanism.")
    assert "1 [hook]" in context and "3 [curiosity]" in context
    assert "12 [development]" in context and "14 [payoff]" in context
    assert "Current section starts at 9" in context and "previous chapter" in context

def test_editorial_final_timing_rejects_late_caption(tmp_path):
    from editorial_standard import final_timing
    path=tmp_path/"captions.srt"
    path.write_text("1\n00:00:01,100 --> 00:00:03,000\nFirst words\n\n2\n00:00:03,000 --> 00:00:04,900\nFinal words\n")
    with pytest.raises(RuntimeError,match="late_first_caption"):
        final_timing(path,5,mode="short")
    path.write_text("1\n00:00:00,200 --> 00:00:03,000\nFirst words\n\n2\n00:00:03,000 --> 00:00:04,900\nFinal words\n")
    assert final_timing(path,5,mode="short")["state"]=="timing_screened"

def test_independent_long_editor_requires_every_verdict():
    from editorial_standard import review_long
    keys=["answers_topic","specific_opening","early_value","coherent_progression","complete_payoff","natural_spoken_language","sustained_specific_interest"]
    data={**dict.fromkeys(keys,True),"reason":"coherent"}
    story=[{"title":str(i),"narration":"Sample chapter"} for i in range(14)]
    def fake(client,prompt,schema,name,validator,**kwargs):
        assert "14. 13" in prompt
        return validator(data)
    with patch("long_generic._retried_json",side_effect=fake):
        assert review_long("Polar lights","de",story,None)["state"]=="model_screened_editorial"
        data["complete_payoff"]=False
        with pytest.raises(RuntimeError,match="complete_payoff"):
            review_long("Polar lights","de",story,None)

def test_photo_text_gate_and_landscape_crop(monkeypatch):
    from source_overlay import check_photo,check_source
    from PIL import Image
    monkeypatch.setenv("PURFFLE_SOURCE_TEXT_GATE","1")
    with patch("source_overlay._text",return_value=[4]):
        with pytest.raises(ValueError,match="source_overlay_text_detected"):
            check_photo(Image.new("RGB",(100,100)))
    with patch("source_overlay._read_frame",return_value=b"png") as reader,patch("source_overlay._text",return_value=[]):
        assert check_source("unused",6,landscape=True)["state"]=="screened"
        assert all(call.args[3] is True for call in reader.call_args_list)


def test_editorial_title_never_invents_unreviewed_promise(tmp_path,monkeypatch):
    from youtube_metadata import attach_title_to_video
    monkeypatch.setenv("PURFFLE_EDITORIAL_STANDARD","1")
    video=tmp_path/"video.mp4"
    video.write_bytes(b"test file")
    (tmp_path/"YouTube_Title.txt").write_text("Volcano Will Destroy the World Tomorrow")
    with patch("youtube_metadata.make_short_title",side_effect=AssertionError("unreviewed title generation forbidden")):
        result=attach_title_to_video({"status":"ok","mp4":str(video),
                                      "topic":"Why Do Volcanoes Erupt?","language":"en"})
    assert result["youtube_title"].startswith("Why Do Volcanoes Erupt?")
    assert result["youtube_title_policy"]=="reviewed_script_or_original_topic"


def test_pacing_prefers_only_meaningful_verified_opening_gain():
    from editorial_pacing import better_opening,pacing_report
    assert better_opening(89,81)
    assert not better_opening(83,81)
    assert not better_opening(60,81)
    assert not better_opening(float("nan"),81)
    proof=pacing_report([3.9,8.1,4.2])
    assert proof["scene_count"]==3 and proof["scenes_over_six_seconds"]==[2]
    assert proof["longest_scene_seconds"]==8.1
    with pytest.raises(ValueError):
        pacing_report([4,float("inf")])

def test_four_scene_volcano_plan_preserves_complete_mechanism_and_distinct_queries():
    from fact_checked_topics import ground_verified_documentary
    from retention_storyboard import audit_storyboard
    from visual_director import build_contract
    for topic,language in [("Why Do Volcanoes Erupt?","en"),("Warum brechen Vulkane aus?","de")]:
        story=ground_verified_documentary({},topic,language,scene_count=4)
        assert len(story["scenes"])==4
        assert len({scene["visual_search_query"] for scene in story["scenes"]})==4
        assert audit_storyboard(topic,None,language,scenes=story["scenes"])["narration_word_count"]>=45
        assert build_contract(story["scenes"][0],topic,1)["family"]=="eruption"
        assert len(ground_verified_documentary({},topic,language,scene_count=3)["scenes"])==3

def test_audience_standard_blocks_empty_clickbait():
    from editorial_standard import audit_structure
    for lang,opening in [("en","You will not believe what happens next."),("de","Du wirst es nicht glauben, was dann passiert.")]:
        with pytest.raises(RuntimeError,match="editorial_empty_clickbait"):
            audit_structure([opening,"A substantive explanation follows with a concrete observation and consequence."],lang,mode="long")

def test_editor_refuses_stiff_or_uninteresting_correct_script():
    from types import SimpleNamespace
    from science_sources import review_topic_answer,Evidence
    story=SimpleNamespace(title="Why do whales dive?",scenes=[SimpleNamespace(narration="Whales dive to feed.")])
    bundle=Evidence("Why do whales dive?",(),"model_screened_reference")
    keys=("answers_question","opening_specific","payoff_complete","early_value","coherent_progression","natural_spoken_language","sustained_specific_interest")
    data={**dict.fromkeys(keys,True),"reason":"editorial test"}
    with patch("science_sources._strict_science_review_json",return_value=data):
        assert review_topic_answer(story,bundle,None)["sustained_specific_interest"]
        for key in ("natural_spoken_language","sustained_specific_interest"):
            data[key]=False
            with pytest.raises(RuntimeError,match=key):
                review_topic_answer(story,bundle,None)
            data[key]=True
