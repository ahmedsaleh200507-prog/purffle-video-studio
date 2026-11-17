"""Regression coverage for consolidated diagnosis and strict scene reports."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import batch
import render_job
from studio_runtime import StrictVisuals


def test_worker_status_does_not_mask_metadata_failure():
    log = ("Worker exited with status 1\n"
           "ValidationError: Scene metadata lacks object/action grounding")
    assert batch.classify_failure("Worker exited with status 1", log) == "metadata_rejected"


def test_worker_voice_timeout_classification():
    assert batch.classify_failure("Worker exited with status 1",
                                  "[VOICE FAILED] Edge TTS deadline exceeded (120s)") == "voice_timeout"


def test_failure_details_expose_scene_and_worker_stage(tmp_path):
    target = tmp_path / "video_02"
    target.mkdir()
    (target / "job-result.json").write_text(json.dumps({
        "error": "No suitable verified REAL VIDEO", "exception_type": "RuntimeError",
        "stage": "production",
    }))
    (target / "footage-report.json").write_text(json.dumps({
        "state": "failed", "provider_events": [{"provider": "pixabay", "status": "empty"}],
        "scenes": [{"index": 3, "status": "failed",
                    "plan": {"visual_search_query": "dolphin brain"},
                    "rejections": [{"source": "wikimedia-video",
                                    "reason": "Scene metadata lacks object/action grounding"}]}]
    }))
    details = batch.failure_details(target)
    assert details["scene"] == 3
    assert details["stage"] == "production"
    assert details["provider"] == "wikimedia-video"
    assert details["rejection_count"] == 1


def test_retry_only_keeps_final_selected_scene(tmp_path, monkeypatch):
    visual = StrictVisuals.__new__(StrictVisuals)
    visual.report = {"scenes": [], "state": "searching"}
    monkeypatch.setattr(visual, "_save", lambda: None)
    calls = []

    def select(idx, query, prompt, topic, need, dest_dir):
        calls.append(query)
        plan = json.loads(prompt)
        if len(calls) == 1:
            visual.report["scenes"].append({
                "index": 1, "status": "failed", "plan": plan,
                "rejections": [{"reason": "metadata rejection"}],
            })
            raise RuntimeError("No suitable verified REAL VIDEO for scene 1")
        visual.report["scenes"].append({
            "index": 1, "status": "selected", "plan": plan,
            "rejections": [], "source": "pixabay", "sha256": "unique",
        })
        return "validated-video"

    monkeypatch.setattr(visual, "for_scene", select)
    plan = {
        "main_character": "", "object": "dolphin", "action": "swimming",
        "location": "ocean", "time": "day", "visual_search_query": "dolphin underwater",
    }
    items = visual.for_scenes([("dolphin underwater", json.dumps(plan), 3.0)],
                              "Dolphins", tmp_path)
    assert items == ["validated-video"]
    assert len(visual.report["scenes"]) == 1
    scene = visual.report["scenes"][0]
    assert scene["status"] == "selected"
    assert len(scene["search_attempts"]) == 1
    assert scene["search_attempts"][0]["status"] == "failed"


def test_repeated_previous_footage_cannot_mask_missing_scene(tmp_path, monkeypatch):
    visual = StrictVisuals.__new__(StrictVisuals)
    visual.report = {"scenes": [], "state": "searching"}
    monkeypatch.setattr(visual, "_save", lambda: None)

    def cannot_find(idx, query, prompt, topic, need, dest_dir):
        visual.report["scenes"].append({
            "index": idx + 1, "status": "failed", "plan": json.loads(prompt),
            "rejections": [],
        })
        raise RuntimeError(f"No suitable verified REAL VIDEO for scene {idx+1}")

    monkeypatch.setattr(visual, "for_scene", cannot_find)
    plan = {
        "main_character": "", "object": "ocean", "action": "moving",
        "location": "sea", "time": "day", "visual_search_query": "ocean waves",
    }
    with pytest.raises(RuntimeError, match="No suitable verified REAL VIDEO"):
        visual.for_scenes([("ocean waves", json.dumps(plan), 4)], "Ocean", tmp_path)
    assert all(s["status"] == "failed" for s in visual.report["scenes"])


def test_diagnostics_include_json_and_mask_keys(tmp_path, monkeypatch):
    monkeypatch.setattr(batch, "ROOT", tmp_path)
    monkeypatch.setenv("GROQ_API_KEY", "supersecret-key")
    target = tmp_path / "finished" / "video_01"
    target.mkdir(parents=True)
    (target / "footage-report.json").write_text(json.dumps({
        "state": "failed", "error": "supersecret-key",
    }))
    batch.write_consolidated_diagnostics(tmp_path / "finished", [{
        "index": 1, "topic": "test", "status": "failed",
        "error": "supersecret-key",
    }])
    text = (tmp_path / "PURFFLE_DIAGNOSTICS.txt").read_text()
    json_text = (tmp_path / "PURFFLE_DIAGNOSTICS.json").read_text()
    assert "supersecret-key" not in text
    assert "supersecret-key" not in json_text
    assert json.loads(json_text)["summary"]["failed"] == 1


def test_output_rejects_duplicate_or_upscaled_scene(tmp_path, monkeypatch):
    from media_validation import QualityValidator
    monkeypatch.setattr(QualityValidator, "validate",
                        lambda *args, **kwargs: {"width": 720, "height": 1280, "duration": 3})
    import subprocess
    monkeypatch.setattr(subprocess, "run",
                        lambda *args, **kwargs: SimpleNamespace(
                            stdout=json.dumps({"streams": [{"codec_type": "audio"}]})))
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake")
    captions = tmp_path / "captions.srt"
    captions.write_text("00:00:00,000 --> 00:00:03,000\nhello")
    report_path = tmp_path / "footage.json"
    base = {"status": "selected", "source": "pixabay", "sha256": "same",
            "license": {"id": "PIXABAY"}, "match": {"visual_score": 0.5},
            "quality": {"portrait_crop_scale": 1.0}}
    report_path.write_text(json.dumps({"scenes": [
        dict(base, index=1), dict(base, index=2)]}))
    with pytest.raises(RuntimeError, match="Duplicate footage"):
        render_job.validate_result(video, {"voice": "edge:test", "timing": "native"},
                                   captions, report_path)
    report_path.write_text(json.dumps({"scenes": [
        dict(base, index=1, sha256="unique", quality={"portrait_crop_scale": 1.5})]}))
    with pytest.raises(RuntimeError, match="insufficient_native_resolution"):
        render_job.validate_result(video, {"voice": "edge:test", "timing": "native"},
                                   captions, report_path)
