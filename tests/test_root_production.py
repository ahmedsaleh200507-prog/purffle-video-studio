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
