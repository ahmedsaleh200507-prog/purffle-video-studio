"""Regression for long video #44943477516: chapter 13 word alignment failure.

No production voice data is used. The approved narrator and actual WAV
timestamps are never substituted with fake or estimated metadata.
"""
from pathlib import Path
import pytest

import approved_reference_voice as voice


def test_long_word_alignment_uses_second_real_asr_without_new_narrator(monkeypatch):
    calls = []
    actual = [("Volcanoes", .11, .40), ("erupt", .43, .80)]

    def asr(text, path, *, model_name="base.en", long_form=False):
        calls.append((model_name, long_form))
        assert long_form
        if model_name == "base.en":
            raise RuntimeError("reference_voice_failed: actual word alignment is incomplete")
        return actual

    monkeypatch.setattr(voice, "check_real_word_timing", asr)
    assert voice.verify_reference_asr(
        "Volcanoes erupt", Path("recorded.wav"), long_form=True
    ) == actual
    assert calls == [("base.en", True), ("small.en", True)]


def test_long_mismatch_uses_second_asr_and_rejects_when_both_fail(monkeypatch):
    calls = []
    def asr(text, path, *, model_name="base.en", long_form=False):
        calls.append(model_name)
        raise RuntimeError("reference_voice_failed: spoken English does not exactly match requested narration")

    monkeypatch.setattr(voice, "check_real_word_timing", asr)
    with pytest.raises(RuntimeError, match="does not exactly match"):
        voice.verify_reference_asr("Volcanoes erupt", Path("recorded.wav"), long_form=True)
    assert calls == ["base.en", "small.en"]


def test_shorts_alignment_stays_strict_no_second_model(monkeypatch):
    calls = []
    def asr(text, path, *, model_name="base.en"):
        calls.append(model_name)
        raise RuntimeError("reference_voice_failed: actual word alignment is incomplete")

    monkeypatch.setattr(voice, "check_real_word_timing", asr)
    with pytest.raises(RuntimeError, match="word alignment"):
        voice.verify_reference_asr("Volcanoes erupt", Path("recorded.wav"),
                                   long_form=False, attempt=3, max_attempts=3)
    assert calls == ["base.en"]


def test_shorts_word_mismatch_only_rescues_on_final_attempt(monkeypatch):
    calls = []
    def asr(text, path, *, model_name="base.en"):
        calls.append(model_name)
        if model_name == "base.en":
            raise RuntimeError("reference_voice_failed: spoken English does not exactly match requested narration")
        return [("Volcanoes", .1, .5), ("erupt", .51, .9)]
    monkeypatch.setattr(voice, "check_real_word_timing", asr)
    with pytest.raises(RuntimeError, match="does not exactly match"):
        voice.verify_reference_asr("Volcanoes erupt", Path("recorded.wav"),
                                   long_form=False, attempt=2, max_attempts=3)
    assert calls == ["base.en"]
    calls.clear()
    assert len(voice.verify_reference_asr(
        "Volcanoes erupt", Path("recorded.wav"),
        long_form=False, attempt=3, max_attempts=3)) == 2
    assert calls == ["base.en", "small.en"]


def test_secondary_runtime_error_does_not_weaken_validation(monkeypatch):
    calls = []
    def asr(text, path, *, model_name="base.en", long_form=False):
        calls.append(model_name)
        if model_name == "small.en":
            raise RuntimeError("reference_voice_failed: actual word alignment is incomplete")
        raise RuntimeError("reference_voice_failed: actual word alignment is incomplete")
    monkeypatch.setattr(voice, "check_real_word_timing", asr)
    with pytest.raises(RuntimeError, match="word alignment"):
        voice.verify_reference_asr("Volcanoes erupt", Path("recorded.wav"), long_form=True)
    assert calls == ["base.en", "small.en"]


def test_long_only_fallback_splits_technical_clause_that_blocked_chapter_eleven():
    original = (
        "When glaciers retreat, they leave behind cirques—amphitheater‑shaped "
        "hollows—and sharp arêtes that expose the volcanic core."
    )
    # Old Shorts strict splitter cannot split at this early three-word comma.
    assert voice._safe_split_for_exact_audio(original) == []
    long_parts = voice._safe_split_for_long_form_audio(original)
    assert len(long_parts) == 2
    assert all(6 <= len(voice._tokens(p)) <= 35 for p in long_parts)
    assert voice._tokens(" ".join(long_parts)) == voice._tokens(original)


def test_long_only_fallback_refuses_too_short_utterances():
    assert voice._safe_split_for_long_form_audio("Ice melts quickly.") == []
    assert voice._safe_split_for_long_form_audio("Lava flows.") == []
