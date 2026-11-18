"""Tests use mocked footage/providers; they are not a real-source production E2E."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from studio_runtime import StrictVisuals, _scene_data, install, strict_prepare_segment, verify_upstream

PLAN = {"main_character": "young man", "object": "euro banknote", "action": "picking up",
        "location": "sidewalk", "time": "daytime",
        "visual_search_query": "young man picking up euro banknote on sidewalk"}


@pytest.fixture
def strict_env(tmp_path, monkeypatch):
    monkeypatch.setenv("FOOTAGE_USED_PATH", str(tmp_path / "ledger.json"))
    monkeypatch.setenv("FOOTAGE_REPORT", str(tmp_path / "report.json"))
    return tmp_path


def candidate(identifier="1", **overrides):
    from purffle_shorts.media import MediaItem
    item = MediaItem("test", identifier, "video", f"https://video.example/{identifier}.mp4", text=PLAN["visual_search_query"])
    item.extra["license"] = {"id": "CC0-1.0", "url": "https://creativecommons.org/publicdomain/zero/1.0/",
                             "creator": "Test creator", "source_page": "https://archive.org/details/test",
                             "attribution": "Test creator | CC0-1.0 | https://archive.org/details/test"}
    for key, value in overrides.items():
        setattr(item, key, value)
    return item


class Registry:
    enabled = ["first", "second"]
    events = []

    def __init__(self, results):
        self.results = results
        self.queries = []

    def search(self, source, query):
        self.queries.append((source, query))
        return self.results.get(source, [])

    def health(self):
        return {s: {"enabled": True} for s in self.enabled}


class Downloader:
    def __init__(self, root):
        self.root = root
        self.urls = []

    def download(self, url):
        self.urls.append(url)
        path = self.root / (str(len(self.urls)) + ".mock-video")
        path.write_bytes(url.encode())
        return path

    def digest(self, path):
        return hashlib.sha256(path.read_bytes()).hexdigest()


class Quality:
    def __init__(self):
        self.calls = []

    def validate(self, path, need=0):
        self.calls.append(need)
        return {"width": 1080, "height": 1920, "duration": 12, "fps": 30, "codec": "h264"}


class Matcher:
    def __init__(self, reject=False):
        self.calls = []
        self.reject = reject

    def match(self, path, spec, metadata="", duration=None):
        self.calls.append((spec, duration))
        if self.reject:
            raise RuntimeError("visual mismatch")
        return {"visual_score": .32, "metadata_score": .8, "crop_focus_x": .5}


def visuals(root, results, matcher=None):
    registry = Registry(results)
    down = Downloader(root)
    quality = Quality()
    obj = StrictVisuals(SimpleNamespace(visual_sources=["first", "second"]), registry=registry,
                        downloader=down, quality=quality, matcher=matcher or Matcher())
    return obj, registry, down, quality


def test_fallback_checks_next_source_without_broadening(strict_env):
    obj, registry, down, quality = visuals(strict_env, {"first": [candidate("bad", kind="image")], "second": [candidate()]})
    got = obj.for_scene(0, "ignored query", json.dumps(PLAN), "unrelated broad topic", 4, strict_env)
    assert got.kind == "video" and got.extra["strict_validated"]
    # Each provider gets the exact request plus subject-focused search variants.
    # Query broadening must not weaken the separate metadata and visual gates.
    expected = [PLAN["visual_search_query"], "euro banknote",
                "euro banknote picking up", "euro banknote sidewalk"]
    assert registry.queries == [(source, query) for source in ("first", "second") for query in expected]
    assert all("euro banknote" in query for _, query in registry.queries)
    assert len(down.urls) == 1 and quality.calls == [4.1]
    report = json.loads((strict_env / "report.json").read_text())
    assert report["scenes"][0]["status"] == "selected"
    assert report["scenes"][0]["quality"]["width"] == 1080
    assert obj.matcher.calls[0][1] == 4  # verify the same prefix the renderer will use


def test_exhaustion_fails_without_generated_filler(strict_env):
    obj, registry, down, _ = visuals(strict_env, {"first": [candidate()]}, Matcher(reject=True))
    with pytest.raises(RuntimeError, match="No suitable verified REAL VIDEO"):
        obj.for_scene(0, "money", json.dumps(PLAN), "money topic", 3, strict_env)
    report = json.loads((strict_env / "report.json").read_text())
    assert report["state"] == "failed" and report["scenes"][0]["status"] == "failed"
    assert "visual mismatch" in report["scenes"][0]["rejections"][0]["reason"]


def test_missing_plan_fails_before_search(strict_env):
    obj, registry, down, _ = visuals(strict_env, {})
    with pytest.raises(RuntimeError, match="Missing structured scene plan"):
        obj.for_scene(0, "money", "generic money image", "topic", 3, strict_env)
    assert registry.queries == [] and down.urls == []


def test_missing_license_never_downloaded(strict_env):
    item = candidate()
    item.extra["license"] = {"id": "CC-BY-SA-4.0"}
    obj, registry, down, _ = visuals(strict_env, {"first": [item]})
    with pytest.raises(RuntimeError, match="No suitable verified REAL VIDEO"):
        obj.for_scene(0, "", json.dumps(PLAN), "", 3, strict_env)
    assert not down.urls


def test_duplicate_ledger_spans_instances(strict_env):
    obj, _, down, _ = visuals(strict_env, {"first": [candidate()]})
    obj.for_scene(0, "", json.dumps(PLAN), "", 3, strict_env)
    again, _, second_down, _ = visuals(strict_env, {"first": [candidate()]})
    with pytest.raises(RuntimeError):
        again.for_scene(0, "", json.dumps(PLAN), "", 3, strict_env)
    assert len(down.urls) == 1 and not second_down.urls


def test_renderer_rejects_stills_and_unvalidated_video(tmp_path):
    settings = SimpleNamespace(width=1080, height=1920, fps=30)
    for item in (candidate(kind="image"), candidate()):
        with pytest.raises(RuntimeError, match="unvalidated footage"):
            strict_prepare_segment(item, 3, 0, settings, tmp_path)


def test_renderer_refuses_looping(tmp_path):
    item = candidate()
    item.path = tmp_path / "file.mp4"
    item.extra["strict_validated"] = True
    item.duration = 2
    with pytest.raises(RuntimeError, match="refusing footage loop"):
        strict_prepare_segment(item, 3, 0, SimpleNamespace(width=1080, height=1920, fps=30), tmp_path)


def test_unaudited_upstream_refused(tmp_path):
    (tmp_path / "script.py").write_text("# different upstream")
    with pytest.raises(RuntimeError, match="Unaudited upstream script.py"):
        verify_upstream(tmp_path)


def test_structured_fields_survive_upstream_normalization():
    verify_upstream()
    install()
    import purffle_shorts.script as script
    data = {"title": "Banknote", "scenes": [{**PLAN, "narration": "A young man reaches for a euro banknote."}]}
    result = script.normalize(data, "banknote", "story", "en")
    assert result.scenes[0].object == "euro banknote"
    assert json.loads(result.scenes[0].image_prompt) == PLAN
    saved = result.to_dict()
    assert saved["scenes"][0]["location"] == "sidewalk"
    assert script.Script.from_dict(saved).scenes[0].visual_search_query == PLAN["visual_search_query"]
    assert all(name in script.SCENE_SCHEMA["required"] for name in PLAN)
    with pytest.raises(ValueError, match="Missing structured scene fields"):
        script.normalize({"scenes": [{"narration": "Anything", "search_query": "anything"}]}, "topic", "facts", "en")


def test_script_normalizer_rewrites_70_fictional_claims_before_tts():
    from fact_checked_topics import ground_lightning_explainer
    verify_upstream()
    install()
    import purffle_shorts.script as script
    topic = "Why Does Lightning Strike the Same Place Again and Again?"
    invented = {
        "title": "Lightning on Elm Street!",
        "description": "Scientists measured 300,000 volts on Elm Street",
        "scenes": [{
            "narration": "That oak was hit 12 times in one storm on Elm Street.",
            "main_character": "", "object": "tree roots", "action": "tap",
            "location": "Elm Street", "time": "",
            "visual_search_query": "tree roots moist soil",
        }]
    }
    output = script.normalize(invented, topic, "story", "en")
    result = output.to_dict()
    assert len(result["scenes"]) == 5
    serialized = json.dumps(result, ensure_ascii=False).lower()
    assert "elm street" not in serialized
    assert "12 times" not in serialized
    assert "300,000" not in serialized
    assert "when you hear thunder" in serialized
    assert result["scenes"][1]["visual_search_query"] == "trees blowing in wind"


def test_structured_plan_never_guesses_object_action():
    with pytest.raises(ValueError, match="Missing structured scene fields"):
        _scene_data({"search_query": "young man money"})


def test_all_ffmpeg_decoders_and_encoders_are_bounded():
    from studio_runtime import bounded_ffmpeg_args
    args = bounded_ffmpeg_args(["-i", "first.mp4", "-i", "second.mp4", "-c:v", "libx264", "result.mp4"])
    assert args[:4] == ["-filter_threads", "1", "-filter_complex_threads", "1"]
    for index, arg in enumerate(args):
        if arg == "-i":
            assert args[index-2:index] == ["-threads", "2"]
    assert args[-3:] == ["-threads", "2", "result.mp4"]


def test_rejected_download_is_discarded(strict_env):
    obj, _, down, _ = visuals(strict_env, {"first": [candidate()]}, Matcher(reject=True))
    with pytest.raises(RuntimeError):
        obj.for_scene(0, "", json.dumps(PLAN), "", 3, strict_env)
    assert not list(strict_env.glob("*.mock-video"))


def test_duplicate_hash_does_not_delete_accepted_footage(strict_env):
    obj, _, _, _ = visuals(strict_env, {"first": [candidate()]})
    accepted = obj.for_scene(0, "", json.dumps(PLAN), "", 3, strict_env)
    obj.registry.results = {"first": [candidate("different-id")]}
    obj.downloader.download = lambda url: accepted.path
    with pytest.raises(RuntimeError):
        obj.for_scene(1, "", json.dumps(PLAN), "", 3, strict_env)
    assert accepted.path.is_file()


def mock_alarm(monkeypatch, *, prior_timer=(0, 0)):
    import signal
    handlers = []
    timers = []
    old_handler = object()
    monkeypatch.setattr(signal, "getsignal", lambda sig: old_handler)
    monkeypatch.setattr(signal, "getitimer", lambda kind: prior_timer)
    monkeypatch.setattr(signal, "signal", lambda sig, handler: handlers.append(handler))
    monkeypatch.setattr(signal, "setitimer", lambda *args: timers.append(args))
    return handlers, timers, old_handler


def test_edge_deadline_escapes_upstream_retries_and_restores_alarm(monkeypatch):
    from studio_runtime import with_edge_deadline
    from purffle_shorts.utils import with_retries
    import signal
    handlers, timers, old_handler = mock_alarm(monkeypatch, prior_timer=(60, 2))
    attempts = []

    def stalled_request():
        attempts.append(1)
        handlers[0](signal.SIGALRM, None)

    with pytest.raises(RuntimeError, match="Edge TTS deadline exceeded"):
        with_edge_deadline(lambda: with_retries(stalled_request, attempts=3), timeout_seconds=180)
    assert attempts == [1]  # BaseException escapes all ordinary Exception retry loops
    assert handlers[-1] is old_handler
    assert timers[0] == (signal.ITIMER_REAL, 180)
    assert timers[1] == (signal.ITIMER_REAL, 0)
    assert 0 < timers[-1][1] <= 60 and timers[-1][2] == 2


def test_edge_native_success_preserved_and_timer_removed(monkeypatch):
    from studio_runtime import with_edge_deadline
    import signal
    handlers, timers, old_handler = mock_alarm(monkeypatch)
    native = SimpleNamespace(engine="edge", timing="native", words=[SimpleNamespace(start=0, end=.5)])
    assert with_edge_deadline(lambda: native) is native
    assert handlers[-1] is old_handler
    assert timers[-1] == (signal.ITIMER_REAL, 0)


def test_edge_deadline_fails_without_main_thread(monkeypatch):
    from studio_runtime import with_edge_deadline
    import threading
    monkeypatch.setattr(threading, "current_thread", lambda: object())
    with pytest.raises(RuntimeError, match="main-thread worker"):
        with_edge_deadline(lambda: None)


def test_async_edge_stream_error_propagates_without_queue_deadlock():
    from studio_runtime import collect_edge_chunks

    class BrokenStream:
        async def stream(self):
            yield {"type": "audio", "data": b"partial"}
            raise OSError("mock websocket refused")

    with pytest.raises(OSError, match="mock websocket refused"):
        collect_edge_chunks(BrokenStream())


def test_async_edge_stream_preserves_audio_and_word_chunks():
    from studio_runtime import collect_edge_chunks
    chunks = [{"type": "audio", "data": b"speech"},
              {"type": "WordBoundary", "text": "Hallo", "offset": 1000000, "duration": 2000000}]

    class NativeStream:
        async def stream(self):
            for chunk in chunks:
                yield chunk

    assert collect_edge_chunks(NativeStream()) == chunks


def test_strict_edge_adapter_returns_native_words(tmp_path, monkeypatch):
    import edge_tts
    import purffle_shorts.utils as utils
    from studio_runtime import strict_edge

    class NativeCommunicate:
        def __init__(self, *args, **kwargs):
            assert kwargs["boundary"] == "WordBoundary"

        async def stream(self):
            yield {"type": "audio", "data": b"mock-encoded-audio"}
            yield {"type": "WordBoundary", "text": "Hallo", "offset": 1000000, "duration": 2000000}

    monkeypatch.setattr(edge_tts, "Communicate", NativeCommunicate)
    monkeypatch.setattr(utils, "with_retries", lambda fn, **kwargs: fn())
    path, words, voice = strict_edge("Hallo", tmp_path,
                                   SimpleNamespace(language="de", tts_voice="", tts_rate="+0%"))
    assert path.read_bytes() == b"mock-encoded-audio"
    assert words[0].text == "Hallo" and words[0].start == .1
    assert words[0].end == pytest.approx(.3) and voice == "de-DE-ConradNeural"


def test_async_edge_stream_has_its_own_deadline():
    import asyncio
    from studio_runtime import collect_edge_chunks

    class StalledStream:
        async def stream(self):
            await asyncio.Event().wait()
            yield {"type": "audio", "data": b"unreachable"}

    with pytest.raises(TimeoutError):
        collect_edge_chunks(StalledStream(), timeout_seconds=.01)


def fake_speech(tmp_path, engine="edge"):
    path = tmp_path / (engine + ".wav")
    path.write_bytes(b"mock audio; waveform decoding is tested separately")
    speech = SimpleNamespace(engine=engine, timing="native" if engine == "edge" else "aligned",
                             audio=path, duration=1.0, voice="test", words=[SimpleNamespace(start=0, end=.7)])
    if engine == "piper":
        speech.provenance = {"engine": "piper", "model": "de_DE-thorsten-medium",
                             "model_url": "https://huggingface.co/approved-model",
                             "model_sha256": "a" * 64,
                             "license": {"id": "CC0-1.0", "url": "https://huggingface.co/approved-model/MODEL_CARD"},
                             "alignment": "native_phoneme_samples"}
    return speech


def voice_settings():
    return SimpleNamespace(offline=False, tts_engine="edge", language="de")


def test_free_voice_prefers_valid_edge_and_records_report(tmp_path, monkeypatch):
    from studio_runtime import speak_with_free_fallback
    monkeypatch.setenv("VOICE_REPORT", str(tmp_path / "voice-report.json"))
    expected = fake_speech(tmp_path)

    def forbidden_fallback():
        raise AssertionError("Local fallback must not run when Edge succeeded")

    result = speak_with_free_fallback(None, tmp_path, voice_settings(), lambda: expected, forbidden_fallback)
    assert result is expected
    report = json.loads((tmp_path / "voice-report.json").read_text())
    assert report["engine"] == "edge" and len(report["attempts"]) == 1


def test_free_voice_falls_back_to_audited_piper_after_edge_failure(tmp_path, monkeypatch):
    from studio_runtime import speak_with_free_fallback
    monkeypatch.setenv("VOICE_REPORT", str(tmp_path / "voice-report.json"))
    expected = fake_speech(tmp_path, "piper")

    def refused_edge():
        raise OSError("websocket 403")

    result = speak_with_free_fallback(None, tmp_path, voice_settings(), refused_edge, lambda: expected)
    assert result is expected
    report = json.loads((tmp_path / "voice-report.json").read_text())
    assert report["engine"] == "piper" and report["timing"] == "aligned"
    assert report["attempts"][0]["status"] == "failed" and "403" in report["attempts"][0]["error"]
    assert report["provenance"]["license"]["id"] == "CC0-1.0"


def test_free_voice_reports_both_failures_and_throws(tmp_path, monkeypatch):
    from studio_runtime import speak_with_free_fallback
    monkeypatch.setenv("VOICE_REPORT", str(tmp_path / "voice-report.json"))

    def failure():
        raise RuntimeError("unavailable")

    with pytest.raises(RuntimeError, match="failed for both Edge and approved local Piper"):
        speak_with_free_fallback(None, tmp_path, voice_settings(), failure, failure)
    report = json.loads((tmp_path / "voice-report.json").read_text())
    assert report["state"] == "failed" and len(report["attempts"]) == 2


@pytest.mark.parametrize("violation", ["license", "engine", "timing", "language", "samples"])
def test_free_voice_rejects_unapproved_local_fallback(tmp_path, monkeypatch, violation):
    from studio_runtime import speak_with_free_fallback
    monkeypatch.setenv("VOICE_REPORT", str(tmp_path / "voice-report.json"))
    rejected = fake_speech(tmp_path, "piper")
    if violation == "license":
        rejected.provenance["license"]["id"] = "Non-Commercial"
    elif violation == "engine":
        rejected.engine = "paid-provider"
    elif violation == "timing":
        rejected.timing = "estimated"
    elif violation == "language":
        rejected.provenance["model"] = "en_US-ljspeech-high"
    elif violation == "samples":
        rejected.provenance["alignment"] = "estimated_samples"

    def edge_failed():
        raise RuntimeError("Edge unavailable")

    with pytest.raises(RuntimeError, match="failed for both"):
        speak_with_free_fallback(None, tmp_path, voice_settings(), edge_failed, lambda: rejected)


class GroundedMatcher(Matcher):
    def validate_metadata(self, spec, metadata):
        from media_validation import SceneMatcher
        return SceneMatcher.validate_metadata(spec, metadata)


@pytest.mark.parametrize("earlier_text", ["person playing guitar on a stage", "man picking euro banknote"])
def test_relevant_fifth_result_outranks_first_four_before_download_limit(strict_env, monkeypatch, earlier_text):
    monkeypatch.setenv("CANDIDATES_PER_SOURCE", "4")
    initial = [candidate(str(i), text=earlier_text, width=2160, height=3840, rank=i) for i in range(4)]
    relevant = candidate("fifth", width=1080, height=1920, rank=4)
    obj, _, down, _ = visuals(strict_env, {"first": initial + [relevant]}, GroundedMatcher())
    got = obj.for_scene(0, "", json.dumps(PLAN), "", 3, strict_env)
    assert got.id == "fifth"
    assert down.urls == [relevant.url]


def test_metadata_ties_prefer_native_portrait_before_api_rank(strict_env):
    portrait = candidate("portrait", width=2160, height=3840, rank=8)
    original_top = candidate("original-top", width=1920, height=1080, rank=0)
    obj, _, down, _ = visuals(strict_env, {"first": [portrait, original_top]}, GroundedMatcher())
    got = obj.for_scene(0, "", json.dumps(PLAN), "", 3, strict_env)
    assert got.id == "portrait" and len(down.urls) == 1


def test_known_native_720p_result_is_allowed(strict_env):
    minimum = candidate("minimum", width=720, height=1280)
    obj, _, down, _ = visuals(strict_env, {"first": [minimum]}, GroundedMatcher())
    got = obj.for_scene(0, "", json.dumps(PLAN), "", 3, strict_env)
    assert got.id == "minimum"
    assert down.urls == [minimum.url]


def test_landscape_720p_requires_upscale_and_is_rejected(strict_env):
    horizontal = candidate("horizontal", width=1280, height=720)
    obj, _, down, _ = visuals(strict_env, {"first": [horizontal]}, GroundedMatcher())
    obj.quality.validate = lambda path, need=0: {
        "width": 1280, "height": 720, "duration": 12, "fps": 30, "codec": "h264",
    }
    with pytest.raises(RuntimeError, match="No suitable verified REAL VIDEO"):
        obj.for_scene(0, "", json.dumps(PLAN), "", 3, strict_env)
    assert down.urls == [horizontal.url]
    assert any("insufficient_native_resolution" in x.get("reason", "")
               for x in obj.report["scenes"][0]["rejections"])


def test_known_below_720p_result_never_downloaded(strict_env):
    low = candidate("low", width=1278, height=719)
    obj, _, down, _ = visuals(strict_env, {"first": [low]}, GroundedMatcher())
    with pytest.raises(RuntimeError, match="No suitable verified REAL VIDEO"):
        obj.for_scene(0, "", json.dumps(PLAN), "", 3, strict_env)
    assert not down.urls
    assert "below 720" in obj.report["scenes"][0]["rejections"][0]["reason"]


@pytest.mark.parametrize("metadata", ["young man picking banknote on sidewalk", "young man euro banknote on sidewalk"])
def test_full_object_and_action_gate_runs_before_download(strict_env, metadata):
    invalid = candidate(text=metadata)
    obj, _, down, _ = visuals(strict_env, {"first": [invalid]}, GroundedMatcher())
    with pytest.raises(RuntimeError, match="No suitable verified REAL VIDEO"):
        obj.for_scene(0, "", json.dumps(PLAN), "", 3, strict_env)
    assert not down.urls
    assert obj.report["scenes"][0]["rejections"][0]["stage"] == "metadata_preflight"


def test_atmospheric_sky_metadata_does_not_require_action_tag():
    from media_validation import SceneMatcher, SceneSpec
    spec = SceneSpec(object="sky", action="glowing", visual_search_query="sky glowing",
                     location="open field")
    assert SceneMatcher.validate_metadata(spec, "blue sky clouds above field") >= .25


def test_atmospheric_exception_never_allows_missing_subject():
    from media_validation import SceneMatcher, SceneSpec, ValidationError
    spec = SceneSpec(object="sky", action="glowing", visual_search_query="sky glowing")
    with pytest.raises(ValidationError):
        SceneMatcher.validate_metadata(spec, "green grass above a field")


def test_atmospheric_exception_does_not_override_human_action():
    from media_validation import SceneMatcher, SceneSpec, ValidationError
    spec = SceneSpec(main_character="young man", object="sky", action="picking up",
                     visual_search_query="young man picking up sky")
    with pytest.raises(ValidationError):
        SceneMatcher.validate_metadata(spec, "blue sky and clouds")


@pytest.mark.parametrize("metadata", [
    "blue sky clouds above field",
    "sky nature background",
    "blue sky overhead",
])
def test_sky_overhead_accepts_subject_without_action_tag(metadata):
    from media_validation import SceneMatcher, SceneSpec
    spec = SceneSpec(object="sky", action="overhead",
                     visual_search_query="blue sky overhead")
    assert SceneMatcher.validate_metadata(spec, metadata) >= .25


def test_sky_exception_requires_real_sky_and_no_character():
    from media_validation import SceneMatcher, SceneSpec, ValidationError
    spec = SceneSpec(object="sky", action="overhead",
                     visual_search_query="blue sky overhead")
    with pytest.raises(ValidationError):
        SceneMatcher.validate_metadata(spec, "blue ocean overhead")
    human = SceneSpec(main_character="young man", object="sky", action="picking up",
                      visual_search_query="young man picking up sky")
    with pytest.raises(ValidationError):
        SceneMatcher.validate_metadata(human, "blue sky overhead")


def test_natural_water_droplets_allow_stock_subject_tags():
    from media_validation import SceneMatcher, SceneSpec
    spec = SceneSpec(object="water droplets", action="sunlight filtering through",
                     visual_search_query="sunlight filtering through water droplets in a lake")
    assert SceneMatcher.validate_metadata(spec, "water droplets rain drops nature lake") >= .15


def test_natural_water_droplets_reject_missing_droplets():
    from media_validation import SceneMatcher, SceneSpec, ValidationError
    spec = SceneSpec(object="water droplets", action="sunlight filtering through",
                     visual_search_query="sunlight filtering through water droplets in a lake")
    with pytest.raises(ValidationError):
        SceneMatcher.validate_metadata(spec, "water lake sunshine landscape")


def test_natural_water_droplets_never_override_character_action():
    from media_validation import SceneMatcher, SceneSpec, ValidationError
    spec = SceneSpec(main_character="woman", object="water droplets", action="collecting",
                     visual_search_query="woman collecting water droplets")
    with pytest.raises(ValidationError):
        SceneMatcher.validate_metadata(spec, "water droplets rain drops nature")



def test_v4_nature_search_expands_droplet_queries(strict_env):
    plan = dict(PLAN, main_character="", object="water droplets",
                action="sunlight filtering through",
                location="lake",
                visual_search_query="sunlight filtering through water droplets in a lake")
    obj, registry, _, _ = visuals(strict_env, {"first": []})
    with pytest.raises(RuntimeError, match="No suitable verified REAL VIDEO"):
        obj.for_scene(0, "", json.dumps(plan), "", 3, strict_env)
    queries = [query for source, query in registry.queries]
    assert "water droplets sunlight" in queries
    assert "water drops in sunlight" in queries
    assert "sunlight reflecting on water" in queries
    assert plan["visual_search_query"] in queries



def test_real_69_archive_pluto_footage_rejected_before_download(strict_env):
    """The #69 volcano short falsely selected this NASA Pluto cryovolcano clip.

    This test verifies the real candidate ID/source-page collision instead of
    relying on CLIP accepting a weak 'magma chamber' similarity score.
    """
    from media_validation import reject_offtopic_science_source, ValidationError
    item = candidate("PlutoInAMinuteEvidenceOfPossibleFrozenVolcanoes")
    item.text = "possible frozen volcanoes, magma chamber"
    item.extra["license"]["source_page"] = (
        "https://archive.org/details/PlutoInAMinuteEvidenceOfPossibleFrozenVolcanoes"
    )
    plan = {"main_character": "", "object": "magma chamber",
            "action": "moving", "location": "", "time": "",
            "visual_search_query": "magma chamber"}
    obj, registry, down, quality = visuals(strict_env, {"first": [item]})
    with pytest.raises(RuntimeError, match="No suitable verified REAL VIDEO"):
        obj.for_scene(1, "magma chamber", json.dumps(plan),
                      "Why Do Some Volcanoes Erupt Without Warning?", 4, strict_env)
    assert down.urls == []
    scene = json.loads((strict_env / "report.json").read_text())["scenes"][0]
    assert any("Off-topic planetary volcanic footage" in entry["reason"]
               for entry in scene["rejections"])


@pytest.mark.parametrize("source_text", [
    "PlutoInAMinuteEvidenceOfPossibleFrozenVolcanoes",
    "https://archive.org/details/PlutoInAMinuteEvidenceOfPossibleFrozenVolcanoes",
    "NASA video: Mars volcano magma chamber",
    "possible volcanoes on Venus",
])
def test_earth_volcano_narration_rejects_explicit_other_planets(source_text):
    from media_validation import reject_offtopic_science_source, ValidationError
    with pytest.raises(ValidationError, match="Off-topic planetary"):
        reject_offtopic_science_source(
            "Why Do Some Volcanoes Erupt Without Warning?", source_text)


@pytest.mark.parametrize("topic,source_text", [
    ("Why Do Some Volcanoes Erupt Without Warning?", "volcano Iceland lava eruption"),
    ("What Causes Volcanoes on Pluto?", "NASA PlutoInAMinuteEvidenceOfPossibleFrozenVolcanoes"),
    ("Can Mars Have Volcanoes?", "Mars volcano documentary"),
    ("Why Do Some Volcanoes Erupt Without Warning?", "NASA Earth volcano eruption"),
    ("Why Does the Ocean Glow at Night?", "NASA Pluto documentary"),
])
def test_related_subjects_or_non_volcanic_topics_remain_eligible(topic, source_text):
    from media_validation import reject_offtopic_science_source
    reject_offtopic_science_source(topic, source_text)
