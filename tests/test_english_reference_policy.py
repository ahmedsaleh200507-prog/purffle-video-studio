"""The user's EN reference speaker must never be silently replaced by Piper Joe.

These are fail-closed production policy checks, NOT voice similarity evidence.
The private 10s WAV is deliberately absent from the public repository.
"""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from english_reference_policy import (
    ENGLISH_REFERENCE_SHA256, ENGLISH_REFERENCE_SECONDS,
    enforce_english_reference_only, requires_reference_only, topic_language)
from studio_runtime import speak_with_free_fallback
from batch import classify_failure


def test_approved_private_audio_fingerprint_is_fixed():
    assert ENGLISH_REFERENCE_SHA256 == (
        "6cc53c46241503f7c6a813ecf98f726eec38bfae33177d624b4ac9190fc41146"
    )
    assert ENGLISH_REFERENCE_SECONDS == 10.0
    assert len(ENGLISH_REFERENCE_SHA256) == 64


def test_strict_english_rejects_other_speaker_instead_of_switching_voice():
    assert requires_reference_only("en", strict=True)
    with pytest.raises(RuntimeError, match="reference_voice_not_ready"):
        enforce_english_reference_only("en", strict=True)
    assert not requires_reference_only("de", strict=True)
    enforce_english_reference_only("de", strict=True)


def test_reference_voice_policy_runs_before_piper_or_edge(tmp_path, monkeypatch):
    monkeypatch.setenv("PURFFLE_STRICT", "1")
    monkeypatch.setenv("PURFFLE_NARRATOR_LOCK", "1")
    called = []
    def old_piper():
        called.append("piper-joe")
        raise AssertionError("Joe must NEVER synthesize a strict EN video")
    def old_edge():
        called.append("edge")
        raise AssertionError("Edge must NEVER synthesize a strict EN video")
    with pytest.raises(RuntimeError, match="reference_voice_not_ready"):
        speak_with_free_fallback(None, tmp_path,
                                 SimpleNamespace(language="en", offline=False,
                                                 tts_engine="edge"),
                                 old_edge, old_piper)
    assert called == []


def test_german_voice_not_blocked_by_english_lock():
    enforce_english_reference_only("de", strict=True)
    assert topic_language("de|Warum ist der Himmel blau?") == "de"
    assert topic_language("en|Why do onions make you cry?") == "en"


def test_production_failure_category_reports_missing_approved_voice():
    message = "reference_voice_not_ready: English reference speaker required"
    assert classify_failure(message, "another provider had http_429") == (
        "approved_english_voice_unavailable")


def test_render_job_preflights_reference_before_media_and_voice():
    root = Path(__file__).resolve().parents[1]
    source = (root / "scripts" / "render_job.py").read_text()
    preflight = source.index("stage = 'voice_identity_preflight'")
    first_install = source.index("install()", preflight)
    media = source.index("prepare_verified_palette(")
    assert preflight < first_install < media
    assert source.count("enforce_english_reference_only(") >= 2


@pytest.mark.parametrize("workflow", ["videos.yml", "long-batch.yml"])
def test_github_workflows_block_wrong_voice_before_downloads(workflow):
    root = Path(__file__).resolve().parents[1]
    yaml = (root / ".github" / "workflows" / workflow).read_text()
    assert "scripts/english_reference_policy.py" in yaml
    setup = ("Install video tools" if workflow == "videos.yml"
             else "Install FFmpeg if absent")
    assert yaml.index("scripts/english_reference_policy.py") < yaml.index(setup)
    if workflow == "videos.yml":
        assert "PURFFLE_NARRATOR_LOCK: '1'" in yaml
    else:
        assert "steps.selected.outputs.language == 'en'" in yaml
        assert "secrets.PURFFLE_REFERENCE_OPUS_B64" in yaml


def test_reference_audio_never_committed_to_public_repo():
    root = Path(__file__).resolve().parents[1]
    for file in root.rglob("*.wav"):
        assert "reference" not in file.name.casefold()
