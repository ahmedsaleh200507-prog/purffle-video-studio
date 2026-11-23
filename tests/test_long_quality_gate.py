"""Regression tests: a nominally 10-minute MP4 must contain documentary content."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from long_quality_gate import (
    DocumentaryQualityError, verify_narration, verify_finished
)


def real_chapters():
    return [
        {"title":f"Distinct chapter {i+1} of our complete story",
         "narration":" ".join(f"chapter{i}_specific_fact{j}"
                              for j in range(105))}
        for i in range(14)
    ]


def real_stock():
    return [
        {"source":"pixabay", "id":str(i), "visual_check":"local_clip_screening"}
        for i in range(14)
    ]


def test_real_full_documentary_script_has_enough_unique_words():
    result=verify_narration(real_chapters())
    assert result["spoken_words"] == 1470
    assert result["narration_not_repeated"]


def test_previous_seven_repeated_offline_sentences_are_rejected():
    facts=["Space telescopes observe distant galaxies and stars."]
    chapters=[
        {"title":f"Scene {i+1}", "narration":facts[0]}
        for i in range(14)
    ]
    with pytest.raises(DocumentaryQualityError, match="only|spoken_words"):
        verify_narration(chapters)


def test_repeated_full_chapters_are_rejected_even_when_length_is_sufficient():
    chapters=real_chapters()
    chapters[13]["narration"]=chapters[0]["narration"]
    with pytest.raises(DocumentaryQualityError, match="repeated"):
        verify_narration(chapters)


def test_verified_14_real_stock_chapters_and_no_long_silence_pass(monkeypatch):
    import long_quality_gate
    monkeypatch.setattr(long_quality_gate.subprocess, "run",
                        lambda *args,**kwargs: SimpleNamespace(
                            returncode=0,stderr=""))
    result=verify_finished(Path("documentary.mp4"),
                           real_chapters(),real_stock())
    assert result["publication_quality"]=="narrated_real_footage_validated"
    assert result["unique_verified_source_videos"]==14


def test_long_narration_gap_invalidates_mp4(monkeypatch):
    import long_quality_gate
    monkeypatch.setattr(long_quality_gate.subprocess, "run",
                        lambda *args,**kwargs: SimpleNamespace(
                            returncode=0,
                            stderr="silence_start: 45.1\nsilence_end: 83.2"))
    with pytest.raises(DocumentaryQualityError,match="silent_gap"):
        verify_finished(Path("documentary.mp4"),
                        real_chapters(),real_stock())


def test_reused_single_clip_is_not_a_long_documentary(monkeypatch):
    import long_quality_gate
    monkeypatch.setattr(long_quality_gate.subprocess, "run",
                        lambda *args,**kwargs: SimpleNamespace(
                            returncode=0,stderr=""))
    with pytest.raises(DocumentaryQualityError,match="insufficient_real_video"):
        verify_finished(Path("documentary.mp4"),
                        real_chapters(),[real_stock()[0]]*14)
