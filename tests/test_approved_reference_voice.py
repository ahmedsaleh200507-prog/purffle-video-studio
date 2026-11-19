"""Reference-only English speech safeguards, offline; no private audio in Git."""
import base64
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import wave

import numpy as np
import pytest

import english_reference_policy as policy
import approved_reference_voice as voice


def wav(tmp_path, seconds=2, rate=24000):
    target=tmp_path/"generated.wav"
    with wave.open(str(target), "wb") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(rate)
        f.writeframes((np.zeros(seconds*rate, dtype=np.int16)).tobytes())
    return target


def test_private_voice_is_required_for_every_english_call(monkeypatch):
    monkeypatch.delenv("PURFFLE_REFERENCE_OPUS_B64", raising=False)
    for strict in (True, False, None):
        with pytest.raises(RuntimeError,match="reference_voice_not_ready"):
            policy.enforce_english_reference_only("en",strict=strict)
    assert policy.requires_reference_only("en",strict=False)
    policy.enforce_english_reference_only("de",strict=True)


def test_mismatched_reference_secret_refused_and_not_printed(monkeypatch):
    wrong=b"OggS" + b"x"*29000
    secret=base64.b64encode(wrong).decode()
    monkeypatch.setenv("PURFFLE_REFERENCE_OPUS_B64",secret)
    with pytest.raises(RuntimeError, match="fingerprint differs") as raised:
        policy.approved_secret_bytes()
    assert secret not in str(raised.value)


def test_approved_secret_can_be_read_only_when_fingerprint_is_pinned(monkeypatch):
    # A fake header/bytes to test the policy; NEVER store or use the user's
    # original private recording in a public GitHub test fixture.
    mock=b"OggS"+b"\x01"*29000
    secret=base64.b64encode(mock).decode()
    monkeypatch.setattr(policy,"ENGLISH_REFERENCE_OPUS_SHA256",
                        hashlib.sha256(mock).hexdigest())
    assert policy.approved_secret_bytes(source=secret)==mock


def test_word_timing_is_on_real_recognized_audio_not_estimated(tmp_path):
    generated=wav(tmp_path)
    words=[
        SimpleNamespace(word="Lightning",start=.04,end=.48,probability=.99),
        SimpleNamespace(word="flashes",start=.52,end=1.02,probability=.99),
    ]
    class ASR:
        def transcribe(self, path, **kwargs):
            assert Path(path)==generated
            assert kwargs["word_timestamps"] is True
            return [SimpleNamespace(words=words)],SimpleNamespace()
    assert voice.check_real_word_timing("Lightning flashes.",generated,
                                        asr_loader=lambda:ASR())==[
        ("Lightning",.04,.48),("flashes",.52,1.02)]
    with pytest.raises(RuntimeError,match="does not exactly match"):
        voice.check_real_word_timing("Thunder flashes.",generated,
                                     asr_loader=lambda:ASR())


def test_speaker_similarity_rejects_unrelated_embedded_voice(tmp_path):
    source=tmp_path/"ref.wav"
    target=tmp_path/"out.wav"
    good=np.ones(32,dtype=np.float32)
    assert voice.voice_similarity(source,target,loader=lambda path:good)>.99
    def bad(path):
        return np.eye(2,32,dtype=np.float32)[0 if path==source else 1]
    with pytest.raises(RuntimeError,match="speaker similarity gate"):
        voice.voice_similarity(source,target,loader=bad)


def test_english_has_no_generic_voice_models_or_production_fallback():
    import local_voice
    assert list(local_voice.VOICES)==["de"]
    assert "en_US-joe-medium" not in repr(local_voice.VOICES)
    root=Path(__file__).resolve().parents[1]
    renderer=(root/"scripts"/"render_job.py").read_text()
    runtime=(root/"scripts"/"studio_runtime.py").read_text()
    assert "voice != 'reference:' + REFERENCE_VOICE_ID" in renderer
    assert "if settings.language == \"en\":" in runtime
    assert "from approved_reference_voice import synthesize as approved_synthesize" in runtime


def test_all_workflows_keep_reference_secret_private():
    root=Path(__file__).resolve().parents[1]/".github"/"workflows"
    workflows=["videos.yml","daily-life-five-20261118.yml",
               "one-german-bathroom-mirror-20261118.yml",
               "one-video-volcanic-island-20261118.yml"]
    for name in workflows:
        content=(root/name).read_text()
        assert "secrets.PURFFLE_REFERENCE_OPUS_B64" in content
        assert "scripts/reference_voice_smoke.py" in content
        assert "PURFFLE_NARRATOR_LOCK: '1'" in content
        assert "chatterbox-tts @ git+https://github.com/resemble-ai/chatterbox.git@ab55923c27757c90cfcc407baa57dc25a7d25217" in content
    assert not list(root.rglob("*approved-reference*.wav"))
