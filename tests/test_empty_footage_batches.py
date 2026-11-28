"""Regression for actual crash in bilingual Pixabay run 46184268072."""
import json
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from studio_runtime import StrictVisuals
from media_validation import SceneMatcher

@pytest.mark.parametrize("pixel_first",["0","1"])
@pytest.mark.parametrize("batch",["empty","used","low_resolution","bad_license"])
def test_batch_without_eligible_candidates_fails_cleanly(tmp_path,monkeypatch,pixel_first,batch):
    import footage_search
    monkeypatch.setenv("PURFFLE_PIXEL_FIRST",pixel_first)
    monkeypatch.setenv("PURFFLE_SHORTS_PORTRAIT_FIRST","0")
    monkeypatch.setenv("PURFFLE_VERIFIED_LIBRARY","0")
    monkeypatch.setenv("PURFFLE_EDITORIAL_PACING","0")
    item=SimpleNamespace(key="clip",source="pixabay",id="clip",url="https://example.org/real.mp4",
        kind="video",width=3840,height=2160,extra={},text="real lava flowing",rank=0)
    if batch=="low_resolution":
        item.width,item.height=640,360
    v=StrictVisuals.__new__(StrictVisuals)
    v.s=SimpleNamespace(width=1080,height=1920)
    v.registry=SimpleNamespace(events=[],health=lambda: [],enabled=["pixabay"])
    v.downloader=SimpleNamespace(download=Mock(side_effect=AssertionError("must not download")))
    v.matcher=SceneMatcher()
    v.sources=["pixabay"]
    v.report={"state":"searching","scenes":[]}
    v._rejected_candidates=set()
    v._technical_rejections={}
    v.used={"clip"} if batch=="used" else set()
    v.used_urls=set()
    v._save=lambda:None
    monkeypatch.setattr(footage_search,"discover",
        lambda *a,**k:iter([("pixabay",[] if batch=="empty" else [item])]))
    query="lava flowing"
    contract={"subject":"lava","queries":[query],"event_required":False}
    plan={"main_character":"","object":"lava","action":"flowing","location":"","time":"",
          "visual_search_query":query,"_visual_contract":contract}
    with pytest.raises(RuntimeError,match="No suitable verified REAL VIDEO"):
        v.for_scene(1,query,json.dumps(plan),"Why do volcanoes erupt?",5.,tmp_path)
    assert v.report["scenes"][0]["status"]=="failed"
    v.downloader.download.assert_not_called()
