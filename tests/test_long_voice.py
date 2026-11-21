"""Long-only ASR tolerance, never touching strict Shorts checks or private voice."""
from pathlib import Path
from types import SimpleNamespace
import wave
import pytest

from approved_reference_voice import (
    _tokens, check_real_word_timing, long_form_asr_deviations,
)
from long_video import voice_segments


def wav(tmp_path):
    f = tmp_path / "sample.wav"
    with wave.open(str(f), "wb") as w:
        w.setframerate(24000)
        w.setnchannels(1)
        w.setsampwidth(2)
        w.writeframes(b"\0\0" * 24000 * 6)
    return f


def fake_recognizer(text):
    tokens = text.split()
    words = [
        SimpleNamespace(word=t, start=0.05 + i * 0.19,
                        end=0.20 + i * 0.19, probability=.96)
        for i,t in enumerate(tokens)
    ]
    class Model:
        def transcribe(self, path, **kwargs):
            assert kwargs["word_timestamps"] is True
            assert kwargs["condition_on_previous_text"] is False
            return [SimpleNamespace(words=words)], SimpleNamespace()
    return lambda: Model()


def test_curly_apostrophes_normalize_to_recognized_spelling():
    assert _tokens("The Earth’s shell.") == _tokens("The Earth's shell.")
    assert _tokens("doesn't") == _tokens("doesnt")


def test_minor_one_word_asr_difference_tolerated_only_in_long_video(tmp_path):
    original = "Volcanoes sometimes build enormous pressure as gas expands beneath the ground before the magma finally escapes at the surface today"
    heard = original.replace("enormous", "extreme")
    assert len(_tokens(original)) >= 20
    with pytest.raises(RuntimeError, match="does not exactly match"):
        check_real_word_timing(original, wav(tmp_path),
                               asr_loader=fake_recognizer(heard))
    real_timing = check_real_word_timing(original, wav(tmp_path),
                                        asr_loader=fake_recognizer(heard),
                                        long_form=True)
    assert len(real_timing) == len(heard.split())
    assert any(token == "extreme" for token, _s, _e in real_timing)


def test_minor_two_word_asr_difference_and_one_missing_word(tmp_path):
    original = "Scientists can learn about volcanoes by watching small earthquakes and measuring hot gases near the surface of the mountain before an eruption happens"
    heard = original.replace("small", "tiny").replace("hot gases", "gases")
    errors, permitted = long_form_asr_deviations(_tokens(original), _tokens(heard))
    assert errors == 2 and permitted
    assert check_real_word_timing(
        original, wav(tmp_path), asr_loader=fake_recognizer(heard),
        long_form=True)


def test_large_omissions_still_rejected(tmp_path):
    original = "Scientists can learn about volcanoes by watching small earthquakes and measuring hot gases near the surface of the mountain before an eruption happens"
    heard = "Scientists can learn about volcanoes by watching small earthquakes"
    with pytest.raises(RuntimeError, match="does not exactly match"):
        check_real_word_timing(original, wav(tmp_path),
                               asr_loader=fake_recognizer(heard),
                               long_form=True)


def test_real_sentence_chunking_does_not_change_spoken_words():
    original = (
        "What happens beneath a volcano before an eruption? "
        "The mountain sits above pockets of molten rock. "
        "Heat causes these underground materials to move. "
        "Escaping gases slowly build up in the cracks. "
        "Sometimes the molten rock reaches the surface. "
        "The moving lava is visible from a great distance. "
        "Scientists measure the shaking underground before issuing alerts."
    )
    pieces = voice_segments(original)
    assert len(pieces) == 6
    assert " ".join(pieces) == original
    assert all(10 <= len(part) <= 350 for part in pieces)
