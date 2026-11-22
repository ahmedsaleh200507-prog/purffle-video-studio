"""Isolated fast tests for arbitrary English/German 10-minute documentaries."""
from types import SimpleNamespace
from unittest.mock import Mock
import json
import pytest

from long_generic import (
    check_long_topic, validate_outline, build_multilingual_documentary,
    SPOKEN_TOTAL
)


def example_outline():
    return {"sections": [
        {"title": f"Section {i}: sea wildlife and real-world observations",
         "visual_search_query": f"ocean sea wildlife waves {i}",
         "visual_subject": "ocean"}
        for i in range(1, 15)
    ]}


def test_outline_requires_exactly_fourteen_grounded_video_searches():
    result=validate_outline(example_outline())
    assert len(result)==14
    assert result[0]["visual_subject"]=="ocean"
    bad=example_outline()
    bad["sections"][0]["visual_subject"]="non visible cosmic consciousness idea"
    with pytest.raises(ValueError,match="outline_bad_heading_or_visual_query"):
        validate_outline(bad)
    bad=example_outline()
    bad["sections"].pop()
    with pytest.raises(ValueError,match="14_chapters"):
        validate_outline(bad)
    bad=example_outline()
    bad["sections"][2]["title"]=bad["sections"][1]["title"]
    with pytest.raises(ValueError):
        validate_outline(bad)


@pytest.mark.parametrize("language,topic", [
    ("en","Why do octopuses have three hearts?"),
    ("de","Warum haben Oktopusse drei Herzen?"),
])
def test_accepts_topic_and_language(language,topic):
    assert check_long_topic(topic,language)==topic


@pytest.mark.parametrize("language,topic", [
    ("fr","Why do octopuses have three hearts?"),
    ("en","Short"),
    ("en","one|two"),
    ("de",""),
])
def test_blocks_bad_long_topics(language,topic):
    with pytest.raises(ValueError):
        check_long_topic(topic,language)


class FakeLongGroq:
    def __init__(self,language):
        self.language=language
        self.calls=[]
        self.chat=SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self,**kwargs):
        self.calls.append(kwargs)
        if "outline" in kwargs["response_format"].get("json_schema",{}).get("name",""):
            obj=example_outline()
        else:
            n=115 if self.language=="en" else 112
            phrase=("The sea reveals remarkable life beneath the ocean waves."
                    if self.language=="en" else
                    "Das Meer zeigt erstaunliches Leben unter den Wellen.")
            text=" ".join([phrase]*30).split()
            # Count token words, not punctuation. Caption and audio must use
            # exactly this returned narration, no later synthesized padding.
            narration=" ".join(text[:n])
            obj={"chapters":[
                {"title":f"Chapter {i}", "narration":narration}
                for i in (1,2)
            ]}
        return SimpleNamespace(choices=[SimpleNamespace(
            finish_reason="stop",
            message=SimpleNamespace(content=json.dumps(obj)))])
            
@pytest.mark.parametrize("language",["en","de"])
def test_generic_workflow_generates_fourteen_language_aware_chapters(language):
    client=FakeLongGroq(language)
    result=build_multilingual_documentary(
        "Why do octopuses have three hearts?" if language=="en" else
        "Warum haben Oktopusse drei Herzen?",
        language,client=client,sleep=lambda _:None)
    assert len(result)==14 and len(client.calls)==8
    assert all(x["visual_search_query"].startswith("ocean") for x in result)
    assert all(x["visual_subject"]=="ocean" for x in result)
    assert SPOKEN_TOTAL[language][0] <= sum(
        len(x["narration"].split()) for x in result) <= SPOKEN_TOTAL[language][1]
    prompts=[request["messages"][-1]["content"] for request in client.calls]
    assert ("German" in prompts[1]) == (language=="de")
    assert all("exactly 2 chapters" in x for x in prompts[1:])
    assert all(x["response_format"]["type"]=="json_schema" for x in client.calls)


def test_long_generic_does_not_rewrite_existing_english_volcano_pilot(monkeypatch):
    import long_video
    import long_generic
    mock=Mock(return_value=[{"title":"Custom chapter"}])
    monkeypatch.setattr(long_generic,"build_multilingual_documentary",mock)
    assert long_video.chapters("Why does the ocean look blue?","en")==[
        {"title":"Custom chapter"}]
    assert mock.call_args.args==("Why does the ocean look blue?","en")
    assert long_video.chapters("Warum brechen Vulkane aus?","de")==[
        {"title":"Custom chapter"}]
    assert mock.call_args.args[1]=="de"


def test_documentary_general_visuals_do_not_get_volcano_queries():
    import long_video
    chapter={"visual_search_query":"octopus coral reef underwater",
             "visual_subject":"octopus"}
    assert long_video.long_expected_subject(0,"Why do octopuses have hearts?",
                                            chapter)=="octopus"
    assert long_video.long_visual_queries(0,"Why do octopuses have hearts?",
                                          chapter)==[
        "octopus coral reef underwater","octopus"]


def test_native_german_voice_selected_only_for_german_long_form(monkeypatch,tmp_path):
    import long_video
    import local_voice
    calls=[]
    def fake_voice(text,out,settings):
        calls.append(settings.language)
        target=tmp_path/"piper-thorsten.wav"
        target.write_bytes(b"wav fixture")
        return SimpleNamespace(
            audio=target,duration=43.0,
            words=[SimpleNamespace(text="Guten",start=.2,end=.6),
                   SimpleNamespace(text="Tag",start=.7,end=1.0)])
    monkeypatch.setattr(local_voice,"synthesize",fake_voice)
    from long_generic import check_long_topic
    data=[{"title":"Wissenschaft","narration":"Die Ozeane leben."}]*14
    audio, captions, duration=long_video.narrate(data,tmp_path,"de")
    assert len(audio)==14 and len(captions)==14
    assert abs(duration-602.0)<.01
    assert calls==["de"]*14
