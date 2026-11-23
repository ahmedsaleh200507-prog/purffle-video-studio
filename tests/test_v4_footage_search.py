from types import SimpleNamespace
import threading
import time
import pytest
from footage_search import discover
from scene_relevance import metadata_evidence, search_queries, suitability
from visual_director import build_contract, metadata_allows


def test_parallel_providers_before_alternative_queries():
    barrier=threading.Barrier(2)
    class Registry:
        def search(self, source, query):
            barrier.wait(timeout=2)
            return [SimpleNamespace(key=source)]
    rows=list(discover(Registry(), ['one','two'], ['exact','alias'], time.monotonic()+5))
    assert {(s,len(c)) for s,c in rows[:2]} == {('one',1),('two',1)}
    assert {(s,len(c)) for s,c in rows[2:]} == {('one',0),('two',0)}


def test_bad_provider_does_not_stop_other_source():
    class Registry:
        def search(self, source, query):
            if source=='bad': raise RuntimeError('credential must not be printed')
            return [SimpleNamespace(key='ok')]
    assert sorted(len(c) for _,c in discover(Registry(),['bad','good'],['lava'],time.monotonic()+2)) == [0,1]


def test_expired_budget_never_queries():
    assert list(discover(None,['one'],['lava'],time.monotonic()-1)) == []


@pytest.mark.parametrize('narration', ['Lava meets ice. The ice melts.', 'Lava contacts ice. Steam rises.', 'Hot lava melts the ice. Steam rises.', 'Lava trifft auf Eis. Das Eis schmilzt.'])
def test_lava_ice_does_not_become_ordinary_volcano(narration):
    plan=dict(narration=narration,object='lava',action='flowing',visual_search_query='lava ice contact')
    contract=build_contract(plan,'What Happens When Lava Meets Ice?',1)
    assert len(contract['sentence_needs']) == 2
    assert contract['family']=='lava_ice_contact'
    assert all('lava' in q for q in contract['queries'])
    assert metadata_evidence(plan,'lava volcano mountain',contract)['contradictions']
    assert not metadata_evidence(plan,'Lava flowing over glacier ice',contract)['contradictions']


def test_later_spoken_event_cannot_hide_behind_first_sentence():
    plan=dict(narration='The volcano stands tall. Then it erupts with an ash plume.',object='volcano',
              action='ambient',visual_search_query='volcano landscape')
    c=build_contract(plan,'Why do volcanoes erupt?',2)
    assert c['sentence_contracts'][1]['event_required']
    assert not metadata_allows(c,'peaceful mountain')
    assert metadata_allows(c,'volcano eruption ash plume')


def test_german_query_translation_and_uncertainty():
    p=dict(object='Gletscher',action='ambient',visual_search_query='Gletscher Eis',location='')
    assert 'glacier ice' in search_queries(p)
    e=metadata_evidence(p,'glacier ice')
    assert e['score']==1 and e['visual_proof'] is False
    r=suitability(e,{'visual_score':.3},{'width':1920,'height':1080})
    assert 'uncalibrated' in r['reliability']


def test_static_catalog_never_reports_verified_remote_api():
    from video_sources import ProviderRegistry
    registry=ProviderRegistry(MediaItem=SimpleNamespace)
    registry.event('freenaturestock-video','ok',count=1)
    report=next(p for p in registry.health() if p['provider']=='freenaturestock-video')
    assert report['integration_type']=='static_catalog'
    assert report['api_test']=='not_applicable_static_catalog'


@pytest.mark.parametrize('text', [
    'Glowing lava enters the ocean and turns seawater into clouds of steam.',
    'Glühende Lava fließt ins Meer und lässt große Dampfwolken aufsteigen.',
])
def test_production95_inland_lava_cannot_fill_ocean_entry(text):
    plan=dict(narration=text,object='volcano',action='ambient',visual_search_query='lava entering ocean steam')
    c=build_contract(plan,'What Happens When Lava Hits the Ocean?',1)
    assert c['family']=='lava_ocean_entry'
    assert all(any(w in q for w in ('ocean','sea')) for q in c['queries'][:3])
    assert not metadata_allows(c,'Volcano lava flow, glowing crater and lava fountain')
    assert metadata_allows(c,'Lava entering ocean and coastal laze steam plume')


def test_production95_eruption_is_not_a_collapsing_lava_coast():
    plan=dict(narration='Sometimes unstable new coastal land collapses, triggering steam explosions at the ocean entry.',
              object='volcano',action='ambient',visual_search_query='lava entering ocean steam')
    c=build_contract(plan,'What Happens When Lava Hits the Ocean?',3)
    assert c['family']=='coastal_lava_collapse'
    assert not metadata_allows(c,'Glowing volcano eruption lava fountain')
    assert metadata_allows(c,'Coastal lava delta collapse ocean steam explosion')


def test_composite_contact_needs_two_supporting_frames_not_one_lucky_match():
    from visual_director import visual_scores
    c={'family':'lava_ocean_entry','event_required':True}
    assert not visual_scores(c, [[.32,.20],[.29,.28],[.28,.29]],opening=True)['verified']
    assert visual_scores(c, [[.34,.20],[.33,.21],[.28,.29]],opening=True)['verified']


def test_discovery_keeps_late_high_relevance_candidates_for_ranking():
    class Registry:
        def search(self, source, query):
            return [SimpleNamespace(key=f"clip-{i}") for i in range(6)]
    rows = list(discover(Registry(), ["source"], ["ocean"], time.monotonic()+3))
    assert len(rows) == 1
    assert [clip.key for clip in rows[0][1]] == [f"clip-{i}" for i in range(6)]


def test_known_unusable_portrait_crop_is_rejected_without_download(tmp_path, monkeypatch):
    from studio_runtime import StrictVisuals
    from types import SimpleNamespace
    from unittest.mock import Mock
    import json
    import footage_search

    candidate = SimpleNamespace(
        key="landscape-1080", source="usgs-video", id="ocean-entry",
        url="https://example.org/real.mp4", kind="video",
        width=1920, height=1080, extra={}, text="real lava entering ocean", rank=1)
    registry = SimpleNamespace(events=[], health=lambda: [], enabled=["usgs-video"])
    downloader = SimpleNamespace(download=Mock(side_effect=AssertionError("never download")))
    visual = StrictVisuals.__new__(StrictVisuals)
    visual.s = SimpleNamespace(width=1080, height=1920)
    visual.registry = registry
    visual.downloader = downloader
    visual.sources = ["usgs-video"]
    visual.report = {"state": "searching", "scenes": []}
    visual._rejected_candidates = set()
    visual._technical_rejections = {}
    visual.used = set()
    visual.used_urls = set()
    visual._save = lambda: None
    monkeypatch.setattr(footage_search, "discover",
                        lambda *args, **kwargs: iter([("usgs-video", [candidate])]))
    plan = {"main_character": "", "object": "lava", "action": "flowing",
            "location": "coast", "time": "day",
            "visual_search_query": "lava entering ocean"}
    with pytest.raises(RuntimeError, match="No suitable verified REAL VIDEO"):
        visual.for_scene(0, plan["visual_search_query"], json.dumps(plan),
                         "Lava meets ocean", 5.0, tmp_path)
    downloader.download.assert_not_called()
    assert "insufficient_native_resolution" in visual.report["scenes"][0]["rejections"][0]["reason"]


def test_event_footage_and_illustrative_context_are_reported_differently():
    from media_first import illustrative_status
    assert illustrative_status({"event_required": True}) is False
    assert illustrative_status({"event_required": False}) is True
    assert illustrative_status(None) is True



def test_explaining_sky_does_not_select_observing_face_as_visual_subject():
    from visual_director import anchor_observational_science_scene
    original = {
        "narration": "This diffuse radiation is what we see when we look upward.",
        "main_character": "person", "object": "eyes", "action": "looking",
        "location": "meadow", "time": "day",
        "visual_search_query": "person looking at sky",
    }
    replacement = anchor_observational_science_scene(
        original, "Why is the sky blue?")
    assert replacement["object"] == "sky"
    assert replacement["main_character"] == ""
    assert "blue" in replacement["visual_search_query"]
    assert replacement["narration"] == original["narration"]
    assert original["object"] == "eyes"
    # A story about a person's face is not automatically discarded.
    assert anchor_observational_science_scene(
        original, "How do people recognize faces?") is original


def test_nature_has_person_and_sunset_hard_negatives_not_generic_silence():
    from media_validation import SceneSpec, scene_specific_hard_negatives
    sky = SceneSpec(object="sky", action="ambient",
                    visual_search_query="clear blue sky")
    clips = scene_specific_hard_negatives(sky)
    assert len(clips) >= 4
    assert any("person walking" in clip for clip in clips)
    assert any("Orange sunset" in clip for clip in clips)
    sunlight = SceneSpec(object="sunlight", action="shining",
                         visual_search_query="sunlight through clouds")
    assert any("silhouette" in clip.lower()
               for clip in scene_specific_hard_negatives(sunlight))
    actor = SceneSpec(main_character="woman", object="eyes",
                      action="looking", visual_search_query="woman looking up")
    assert not scene_specific_hard_negatives(actor)


def test_clear_blue_sky_rejects_visuals_that_look_more_like_gray_sky(tmp_path, monkeypatch):
    from media_validation import SceneSpec, SceneMatcher, ValidationError
    from PIL import Image
    spec = SceneSpec(object="sky", action="ambient", visual_search_query="clear blue sky")
    monkeypatch.setattr("media_validation._frame",
                        lambda *args, **kwargs: Image.new("RGB", (224, 224)))
    captions_seen = []
    def fake_scores(frames, captions):
        captions_seen.extend(captions)
        # A distractor scene scores better than requested blue sky
        return [[.267, .24] + [.18]*(len(captions)-3) + [.285]] * len(frames)
    monkeypatch.setattr(SceneMatcher, "_similarities", fake_scores)
    with pytest.raises(ValidationError, match="Visual scene mismatch"):
        SceneMatcher().match(tmp_path / "fake.mp4", spec, "clear blue sky clouds",
                             duration=6)
    assert any("gray overcast" in c.lower() for c in captions_seen)
    assert any("person walking" in c for c in captions_seen)
