"""Offline contract tests for PRIVATE reference voice audition (not a live clone)."""
from pathlib import Path
import hashlib
import json
import wave

import numpy as np
import pytest

from reference_voice_audition import generate_audition, validate_reference


def sample(tmp_path, seconds=8, rate=16000):
    source = tmp_path / "private-reference.wav"
    with wave.open(str(source), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((np.zeros(seconds * rate, dtype=np.int16)).tobytes())
    return source, hashlib.sha256(source.read_bytes()).hexdigest()


def test_reference_identity_pinned(tmp_path):
    file, digest = sample(tmp_path)
    report = validate_reference(file, digest)
    assert report["sha256"] == digest
    assert report["seconds"] == 8


def test_changed_reference_aborts_before_inference(tmp_path):
    file, digest = sample(tmp_path)
    file.write_bytes(file.read_bytes()[:-12] + b"corrupt WAV!")
    with pytest.raises(RuntimeError, match="reference_voice_changed"):
        validate_reference(file, digest)


def test_too_short_or_unapproved_language_fails(tmp_path):
    file, digest = sample(tmp_path, seconds=3)
    with pytest.raises(RuntimeError, match="require 6-15s"):
        validate_reference(file, digest)
    file, digest = sample(tmp_path, seconds=8)
    with pytest.raises(RuntimeError, match="language_invalid"):
        generate_audition(reference=file, expected_sha256=digest,
                         text="A real narration test.", language="fr",
                         output=tmp_path / "out.wav",
                         transcript="Test", model_loader=lambda: None)


def test_full_voice_clone_requires_exact_reference_transcript(tmp_path):
    file, digest = sample(tmp_path)
    with pytest.raises(RuntimeError, match="transcript_required"):
        generate_audition(reference=file, expected_sha256=digest,
                         text="A real narration test.", language="en",
                         output=tmp_path / "out.wav", model_loader=lambda: None)


def test_offline_fake_model_can_audition_but_never_claim_identical(tmp_path):
    file, digest = sample(tmp_path)

    class Model:
        def create_voice_clone_prompt(self, **kwargs):
            assert kwargs["ref_audio"] == str(file)
            assert kwargs["ref_text"] == "These words are genuinely in the source."
            assert kwargs["x_vector_only_mode"] is False
            return ["speaker_profile"]
        def generate_voice_clone(self, **kwargs):
            assert kwargs["language"] == "English"
            assert kwargs["voice_clone_prompt"] == ["speaker_profile"]
            return [np.sin(2 * np.pi * 120 * np.arange(24000) / 24000)], 24000

    target = tmp_path / "audition.wav"
    report = generate_audition(reference=file, expected_sha256=digest,
                              text="The boiling onions release an irritating gas.",
                              language="en", output=target,
                              transcript="These words are genuinely in the source.",
                              model_loader=lambda: Model())
    assert target.stat().st_size > 16000
    assert report["state"] == "audition_only_unverified_similarity"
    assert "Not an identical-voice certificate" in report["warning"]
    assert not Path(__file__).parents[1].joinpath("reference_voice.wav").exists()
    assert json.loads(target.with_suffix(".voice-report.json").read_text())["model"].startswith("Qwen")


def test_xvector_only_marked_as_lower_fidelity(tmp_path):
    file, digest = sample(tmp_path)
    class Fake:
        def create_voice_clone_prompt(self, **kwargs):
            assert kwargs["x_vector_only_mode"] is True
            return []
        def generate_voice_clone(self, **kwargs):
            return [np.ones(16000, dtype=np.float32) * 0.1], 16000
    report = generate_audition(reference=file, expected_sha256=digest,
                              text="Something is happening here.", language="de",
                              output=tmp_path/"german.wav", x_vector_only=True,
                              model_loader=lambda: Fake())
    assert report["language"] == "de"


def test_never_changes_production_speaker_or_synchronization():
    repo = Path(__file__).parents[1]
    voice = (repo / "scripts" / "local_voice.py").read_text()
    assert "'en_US-joe-medium'" in voice and "'en_US-ljspeech-high'" not in voice
    assert "'de_DE-thorsten-medium'" in voice
    runtime = (repo / "scripts" / "studio_runtime.py").read_text()
    assert "reference_voice_audition" not in runtime
    assert "reference_voice_audition" not in (repo / ".github" / "workflows" / "videos.yml").read_text()
