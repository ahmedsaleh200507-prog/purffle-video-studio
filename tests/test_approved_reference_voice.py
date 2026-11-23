"""Reference-only English speech safeguards, offline; no private audio in Git."""
import base64
import hashlib
import json
import os
import sys
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


def test_v4_english_uses_pinned_joe_without_private_secret():
    from english_reference_policy import requires_reference_only, enforce_english_reference_only
    from local_voice import provenance
    assert not requires_reference_only('en')
    enforce_english_reference_only('en')
    assert provenance('en')['model']=='en_US-joe-medium'


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


def test_v4_fixed_voices_and_no_reference_production_fallback():
    import local_voice
    assert set(local_voice.VOICES)=={'en','de'}
    assert local_voice.provenance('en')['model']=='en_US-joe-medium'
    root=Path(__file__).resolve().parents[1]
    runtime=(root/'scripts/studio_runtime.py').read_text()
    active=runtime[runtime.index('def speak_with_free_fallback'):runtime.index('def install')]
    assert 'approved_reference_voice' not in active


def test_production_does_not_export_or_install_private_reference():
    root=Path(__file__).resolve().parents[1]/'.github/workflows'
    for name in ('videos.yml','long-batch.yml'):
        content=(root/name).read_text()
        assert 'secrets.PURFFLE_REFERENCE_OPUS_B64' not in content
        assert 'chatterbox-tts' not in content
        assert 'actions/upload-artifact@' in content



def test_private_voice_launch_keeps_venv_python_symlink(tmp_path, monkeypatch):
    """The actual failure in live #5 was resolving the venv python symlink.

    The system executable exists, but cannot import the Nano model that was
    intentionally installed only inside the dedicated virtual environment.
    """
    interpreter = tmp_path / "private-venv" / "bin" / "python"
    interpreter.parent.mkdir(parents=True)
    interpreter.symlink_to(sys.executable)
    monkeypatch.setenv("PURFFLE_REFERENCE_PYTHON", str(interpreter))
    selected = voice._model_interpreter()
    assert selected == interpreter
    assert selected.is_symlink()
    assert selected.resolve() != selected
    assert selected.is_file()


def test_private_voice_launch_uses_absolute_path_without_following_symlinks(tmp_path, monkeypatch):
    interpreter = tmp_path / "private-venv" / "bin" / "python"
    interpreter.parent.mkdir(parents=True)
    interpreter.symlink_to(sys.executable)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PURFFLE_REFERENCE_PYTHON",
                       "private-venv/bin/python")
    assert voice._model_interpreter() == interpreter
