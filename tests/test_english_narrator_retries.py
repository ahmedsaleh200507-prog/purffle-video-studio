"""Offline regression for #73: retry only the same approved private speaker.

No real voice reference, credentials, network, or media models required.
"""
from pathlib import Path
from types import SimpleNamespace
import sys
import wave
import types

import pytest
import approved_reference_voice as voice


def _write_wav(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(24000)
        audio.writeframes(b"\x00\x00" * (24000 * 2))


def _prepare(monkeypatch, seeds):
    # Lightweight CI intentionally does not install the expensive upstream
    # media library. Stub only the two return classes, not the voice logic.
    package = types.ModuleType("purffle_shorts")
    package.__path__ = []
    timing = types.ModuleType("purffle_shorts.timing")
    timing.Word = lambda word, start, end: SimpleNamespace(
        text=word, word=word, start=start, end=end)
    tts = types.ModuleType("purffle_shorts.tts")
    tts.Speech = lambda audio, words, duration, engine, speaker, timing: SimpleNamespace(
        audio=audio, words=words, duration=duration,
        engine=engine, voice=speaker, timing=timing)
    monkeypatch.setitem(sys.modules, "purffle_shorts", package)
    monkeypatch.setitem(sys.modules, "purffle_shorts.timing", timing)
    monkeypatch.setitem(sys.modules, "purffle_shorts.tts", tts)
    monkeypatch.setattr(voice, "approved_secret_bytes", lambda: b"private-but-not-a-real-recording")
    def reference(folder):
        path = folder / "approved-reference.wav"
        _write_wav(path)
        return path
    monkeypatch.setattr(voice, "prepare_reference", reference)
    monkeypatch.setattr(voice, "voice_similarity", lambda _ref, _out: 0.9)
    monkeypatch.setattr(voice, "_model_interpreter", lambda: Path(sys.executable))
    def worker(cmd, *, timeout, stage):
        assert "--reference" in cmd
        assert "--seed" in cmd
        assert stage == "nano-reference-worker"
        seeds.append(int(cmd[cmd.index("--seed") + 1]))
        _write_wav(cmd[cmd.index("--wav") + 1])
    monkeypatch.setattr(voice, "_run", worker)


def test_failed_exact_asr_is_regenerated_with_same_speaker(monkeypatch, tmp_path):
    seeds, checks = [], []
    _prepare(monkeypatch, seeds)
    def verify(text, _wav):
        checks.append(text)
        if len(checks) == 1:
            raise RuntimeError("reference_voice_failed: spoken English does not exactly match requested narration")
        return [(word, i * .25, i * .25 + .2)
                for i, word in enumerate(text.rstrip(".").split())]
    monkeypatch.setattr(voice, "check_real_word_timing", verify)
    narration = "Lightning flashes across the night sky."
    speech = voice.synthesize(narration, tmp_path, SimpleNamespace(language="en"))
    assert seeds == [190526, 220917]
    assert len(checks) == 2
    assert speech.provenance["synthesis_attempts"] == 2
    assert speech.provenance["reference_private"] is True
    assert speech.provenance["speaker_similarity_cosine"] == .9
    assert len(speech.words) == 6


def test_rejects_all_inaccurate_attempts_without_accepting_mismatch(monkeypatch, tmp_path):
    seeds = []
    _prepare(monkeypatch, seeds)
    monkeypatch.setattr(voice, "check_real_word_timing",
                        lambda *_: (_ for _ in ()).throw(
                            RuntimeError("reference_voice_failed: incorrect transcription")))
    with pytest.raises(RuntimeError, match="all approved-reference narration attempts failed"):
        voice.synthesize("Lightning flashes across the night sky.",
                         tmp_path, SimpleNamespace(language="en"))
    assert seeds == [190526, 220917, 314159]
    assert not (tmp_path / "voice-reference.wav").exists()


def test_verified_short_scenes_are_joined_without_estimated_caption_times(monkeypatch, tmp_path):
    seeds = []
    _prepare(monkeypatch, seeds)
    parts = [
        "Glowing lava pours into the ocean and creates huge clouds of steam.",
        "Water evaporates rapidly while the glowing volcanic rock begins to cool.",
    ]
    def verify(text, path):
        # Simulate strict real-ASR word verification on EACH generated audio.
        assert text in parts
        assert path.is_file()
        return [(w, i * .12, i * .12 + .09)
                for i, w in enumerate(text.rstrip(".").split())]
    monkeypatch.setattr(voice, "check_real_word_timing", verify)
    speech = voice.synthesize(
        " ".join(parts), tmp_path, SimpleNamespace(language="en"),
        segments=parts)
    assert seeds == [190526, 190526]
    assert speech.provenance["verified_scene_segments"] == 2
    assert speech.provenance["synthesis_attempts"] == 2
    assert speech.provenance["speaker_similarity_cosine"] == .9
    assert len(speech.words) == sum(len(p.split()) for p in parts)
    assert speech.words[len(parts[0].split())].start >= 2.14
    assert abs(speech.duration - 4.14) < .03
    assert speech.audio.is_file()


def test_invalid_scene_split_never_silently_changes_spoken_text(monkeypatch, tmp_path):
    seeds = []
    _prepare(monkeypatch, seeds)
    monkeypatch.setattr(voice, "check_real_word_timing", lambda text, _wav: [
        (w, i * .25, i * .25 + .2)
        for i, w in enumerate(text.rstrip(".").split())
    ])
    spoken = "Lightning and thunder happen together."
    speech = voice.synthesize(
        spoken, tmp_path, SimpleNamespace(language="en"),
        segments=["This is not the actual requested narration."])
    assert speech.provenance["verified_scene_segments"] == 1
    assert seeds == [190526]


def test_production_82_rescues_repeated_words_by_verifying_exact_short_clauses(monkeypatch, tmp_path):
    """#82: real Nano produced sound but all three long-utterance ASR checks failed.

    Retry the ORIGINAL words as smaller phrases with the SAME private
    reference, verify their actual WAV/ASR independently, and stitch measured
    word times. No text changes, forced alignment guesses or other speaker.
    """
    seeds = []
    _prepare(monkeypatch, seeds)
    first = "Solid steel sinks. But this giant steel ship stays afloat."
    second = "Its wide hollow hull holds air and displaces water."
    checks = []
    def verify(text, path):
        checks.append(text)
        assert Path(path).is_file()
        if text == first:
            raise RuntimeError("reference_voice_failed: spoken English does not exactly match requested narration")
        return [(token, i * .12, i * .12 + .09)
                for i, token in enumerate(voice._tokens(text))]
    monkeypatch.setattr(voice, "check_real_word_timing", verify)

    speech = voice.synthesize(first + " " + second, tmp_path,
                              SimpleNamespace(language="en"),
                              segments=[first, second])
    assert seeds == [190526, 220917, 314159, 190526, 190526, 190526]
    assert checks[:3] == [first] * 3
    assert checks[3:5] == ["Solid steel sinks.", "But this giant steel ship stays afloat."]
    assert checks[-1] == second
    assert [w.text for w in speech.words] == voice._tokens(first + " " + second)
    assert speech.provenance["voice"] == voice.REFERENCE_VOICE_ID
    assert speech.provenance["speaker_similarity_cosine"] == .9
    assert speech.provenance["verified_scene_segments"] == 2
    assert speech.provenance["synthesis_attempts"] == 6
    assert speech.audio.is_file()


def test_voice_rescue_never_alters_words_or_accepts_unverified_chunks(monkeypatch, tmp_path):
    seeds = []
    _prepare(monkeypatch, seeds)
    first = "Solid steel sinks. But this giant steel ship stays afloat."
    assert voice._safe_split_for_exact_audio(first) == [
        "Solid steel sinks.", "But this giant steel ship stays afloat."]
    assert voice._safe_split_for_exact_audio("Steel sinks. Ships float.") == [
        "Steel sinks.", "Ships float."]
    assert voice._safe_split_for_exact_audio("Steel sinks quickly.") == []
    monkeypatch.setattr(voice, "check_real_word_timing",
                        lambda *_: (_ for _ in ()).throw(
                            RuntimeError("reference_voice_failed: spoken English does not exactly match requested narration")))
    with pytest.raises(RuntimeError, match="all approved-reference narration attempts failed"):
        voice.synthesize(first, tmp_path, SimpleNamespace(language="en"))
    assert not (tmp_path / "voice-reference.wav").exists()
