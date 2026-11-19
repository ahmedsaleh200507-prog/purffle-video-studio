"""The real MP4 must open with moving footage AND audible narration.

This is engineering QA, never a promise of retention or revenue.
"""
from array import array
import math
from pathlib import Path

import pytest

from shorts_final_qa import audit_rendered_opening, evaluate_voice_samples


def pcm_with_voice(*, onset: float, voice_seconds: float = 1.2, length: float = 2.0,
                   sample_rate: int = 16000) -> bytes:
    values = array("h")
    for i in range(int(length * sample_rate)):
        seconds = i / sample_rate
        if onset <= seconds < onset + voice_seconds:
            sample = round(8500 * math.sin(2 * math.pi * 190 * seconds))
        else:
            sample = 0
        values.append(sample)
    return values.tobytes()


def test_audible_hook_starts_in_the_first_second():
    result = evaluate_voice_samples(pcm_with_voice(onset=0.25))
    assert result["passed"]
    assert result["first_audio_seconds"] <= 0.4
    assert result["audible_windows_first_two_seconds"] >= 3


def test_silent_or_delayed_opening_fails_regardless_of_audio_later():
    for sound in (
        pcm_with_voice(onset=0.95, voice_seconds=1.0),
        pcm_with_voice(onset=1.45, voice_seconds=0.5),
        pcm_with_voice(onset=0.0, voice_seconds=0.0),
        b"",
    ):
        assert evaluate_voice_samples(sound)["passed"] is False


def test_early_silent_intro_cannot_be_masked_by_motion():
    frame = {"verified": True, "motion": 5, "impact": 79}
    with pytest.raises(RuntimeError, match="narration not audible"):
        audit_rendered_opening(
            Path("mock.mp4"),
            frame_analyzer=lambda _: frame,
            audio_analyzer=lambda _: {"passed": False, "first_audio_seconds": 1.2})


def test_early_static_black_intro_cannot_be_masked_by_narrator():
    with pytest.raises(RuntimeError, match="dark/static/blank"):
        audit_rendered_opening(
            Path("mock.mp4"),
            frame_analyzer=lambda _: {"verified": False, "reason": "blank"},
            audio_analyzer=lambda _: {"passed": True, "first_audio_seconds": .1})


def test_both_final_checks_must_pass_on_rendered_output():
    report = audit_rendered_opening(
        Path("mock.mp4"),
        frame_analyzer=lambda _: {"verified": True, "impact": 82},
        audio_analyzer=lambda _: {"passed": True, "first_audio_seconds": 0.2})
    assert report["state"] == "passed"
    assert report["opening_visual_review"]["impact"] == 82
    assert report["opening_narration_review"]["first_audio_seconds"] == 0.2
    assert "not YouTube viewer-retention measurement" in report["note"]


def test_final_opening_gate_is_mandatory_before_mp4_marked_successful():
    code = (Path(__file__).resolve().parents[1] /
            "scripts" / "render_job.py").read_text(encoding="utf-8")
    assert code.index("audit_rendered_opening(video)") < code.index("result.update(status='ok'")
    assert "opening_quality_unverified: real opening selection proof missing" in code
    assert "'final_opening_qa': final_opening" in code
    assert "stage = 'final_opening_qa'" in code
    assert "hook_overlay=False" in code
