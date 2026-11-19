"""Strictly ONE English narrator: the user's pinned private reference.

The older generic English Piper voices are deleted. No fallback to Edge.
German's existing pinned Thorsten remains supported and regression-tested.
"""
from pathlib import Path
from types import SimpleNamespace
import json

import pytest
import local_voice
from studio_runtime import speak_with_free_fallback
from english_reference_policy import (
    ENGLISH_REFERENCE_SHA256, REFERENCE_VOICE_ID, approved_secret_bytes,
)


def test_all_generic_english_piper_models_were_physically_removed():
    assert list(local_voice.VOICES) == ["de"]
    assert "en_US-joe-medium" not in str(local_voice.VOICES)
    assert "en_US-ljspeech-high" not in str(local_voice.VOICES)
    with pytest.raises(RuntimeError, match="removed"):
        local_voice.provenance("en")
    with pytest.raises(RuntimeError, match="removed"):
        local_voice._voice_key("en")


def test_german_thorsten_remains_fixed_and_cc0(monkeypatch):
    monkeypatch.setenv("PURFFLE_NARRATOR_LOCK", "1")
    voice = local_voice.provenance("de")
    assert voice["model"] == "de_DE-thorsten-medium"
    assert voice["license"]["id"] == "CC0-1.0"
    assert voice["alignment"] == "native_phoneme_samples"


def test_reference_voice_identifies_one_fixed_speaker_only():
    assert REFERENCE_VOICE_ID.startswith("approved-reference-male-")
    assert REFERENCE_VOICE_ID.endswith(ENGLISH_REFERENCE_SHA256[:16])


def test_english_without_approved_secret_refuses_all_fallbacks(tmp_path, monkeypatch):
    monkeypatch.delenv("PURFFLE_REFERENCE_OPUS_B64", raising=False)
    monkeypatch.setenv("VOICE_REPORT", str(tmp_path / "voice-report.json"))
    callbacks = []
    def forbidden():
        callbacks.append("wrong_voice")
        raise AssertionError("No generic English speaker is allowed")
    with pytest.raises(RuntimeError, match="reference_voice_not_ready"):
        speak_with_free_fallback(SimpleNamespace(narration="An explanation"),
                                 tmp_path,
                                 SimpleNamespace(language="en", offline=False,
                                                 tts_engine="edge"),
                                 forbidden, forbidden)
    assert callbacks == []


def test_german_locked_narrator_cannot_fall_back_to_english(tmp_path, monkeypatch):
    monkeypatch.setenv("PURFFLE_NARRATOR_LOCK", "1")
    monkeypatch.setenv("VOICE_REPORT", str(tmp_path / "voice-report.json"))
    speech = SimpleNamespace(
        engine="piper", voice="en_US-joe-medium",
        audio=tmp_path / "audio.wav", duration=2.,
        timing="aligned", words=[SimpleNamespace(start=0., end=1.)],
        provenance={"model":"en_US-joe-medium"})
    speech.audio.write_bytes(b"not empty")
    with pytest.raises(RuntimeError, match="Locked male narrator unavailable"):
        speak_with_free_fallback(None, tmp_path,
            SimpleNamespace(language="de", offline=False, tts_engine="edge"),
            lambda: pytest.fail("Edge may not run"), lambda: speech)
    report=json.loads((tmp_path/"voice-report.json").read_text())
    assert report["state"] == "failed"
    assert [x["engine"] for x in report["attempts"]] == ["piper"]
