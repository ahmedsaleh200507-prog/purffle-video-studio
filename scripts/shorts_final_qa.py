"""Independent last-mile Shorts opening QA on the ACTUAL rendered MP4.

Preflight scores source footage; this also checks that FFmpeg/render/caption
compositing did not accidentally put a blank/still opening or long silent lead
into the output. Passing is technical readiness, NEVER a promise of views.
"""
from __future__ import annotations

from array import array
import math
from pathlib import Path
import shutil
import subprocess
import sys


def evaluate_voice_samples(data: bytes, *, rate: int = 16000,
                           window_seconds: float = 0.10) -> dict:
    """Estimate narration onset in uncompressed PCM from finished MP4.

    Only sound is analyzed; the separate locked voice/ASR gate certifies
    whether it is the approved narrator and the real words were spoken.
    """
    if rate <= 0 or len(data) < rate // 2:
        return {"passed": False, "reason": "opening_audio_missing_or_short"}
    raw = array("h")
    raw.frombytes(data[:len(data) - len(data) % 2])
    if sys.byteorder != "little":
        raw.byteswap()
    window = max(1, round(window_seconds * rate))
    energies = []
    for at in range(0, min(len(raw), int(rate * 2.0)), window):
        samples = raw[at:at + window]
        if len(samples) < window // 2:
            break
        rms = math.sqrt(sum(sample * sample for sample in samples) / len(samples))
        energies.append(rms / 32768.0)
    # -40 dBFS average speech energy. AAC compression noise by itself should
    # not count as a genuine spoken introduction.
    voiced = [idx for idx, val in enumerate(energies)
              if val >= 0.01]
    onset = round(voiced[0] * window_seconds, 3) if voiced else None
    # The spoken narration should begin within the first 0.8 seconds.
    passed = bool(voiced and onset <= 0.8
                  and sum(value >= 0.01 for value in energies) >= 3)
    return {
        "passed": passed,
        "reason": "immediate_opening_narration" if passed else
                  "late_or_silent_opening_audio",
        "first_audio_seconds": onset,
        "audible_windows_first_two_seconds": len(voiced),
        "seconds_analyzed": round(len(energies) * window_seconds, 2),
    }


def inspect_output_audio(path: Path) -> dict:
    binary = shutil.which("ffmpeg")
    if not binary:
        raise RuntimeError("shorts_final_qa_unavailable: ffmpeg missing")
    try:
        p = subprocess.run(
            [binary, "-hide_banner", "-nostdin", "-loglevel", "error",
             "-i", str(path), "-map", "0:a:0", "-vn", "-t", "2",
             "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("shorts_final_qa_unavailable: audio probe failed") from exc
    if p.returncode:
        raise RuntimeError("shorts_final_qa_unavailable: cannot decode narration")
    return evaluate_voice_samples(p.stdout)


def audit_rendered_opening(video: Path, *, frame_analyzer=None,
                           audio_analyzer=None) -> dict:
    from opening_impact import inspect_opening
    frame_analyzer = frame_analyzer or inspect_opening
    audio_analyzer = audio_analyzer or inspect_output_audio
    try:
        visual = dict(frame_analyzer(video))
        audio = dict(audio_analyzer(video))
    except (OSError, ValueError) as exc:
        raise RuntimeError("shorts_final_qa_unavailable: cannot inspect rendered intro") from exc
    valid_visual = visual.get("verified") is True
    valid_audio = audio.get("passed") is True
    result = {
        "state": "passed" if valid_visual and valid_audio else "failed",
        "opening_visual_review": visual,
        "opening_narration_review": audio,
        "note": "Technical first-two-seconds check; not YouTube viewer-retention measurement",
    }
    if not valid_visual:
        raise RuntimeError("shorts_final_opening_failed: dark/static/blank first frames")
    if not valid_audio:
        raise RuntimeError("shorts_final_opening_failed: narration not audible at beginning")
    return result
