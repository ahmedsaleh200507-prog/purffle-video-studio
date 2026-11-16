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
        return {"width": 1920, "height": 1080, "duration": 12, "fps": 30, "codec": "h264"}


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
    assert registry.queries == [("first", PLAN["visual_search_query"]), ("second", PLAN["visual_search_query"])]
    assert len(down.urls) == 1 and quality.calls == [4.1]
    report = json.loads((strict_env / "report.json").read_text())
    assert report["scenes"][0]["status"] == "selected"
    assert report["scenes"][0]["quality"]["width"] == 1920
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
