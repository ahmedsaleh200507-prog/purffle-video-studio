"""Narrow, observable-color evidence for sky-blue educational B-roll.

CLIP alone can score *gray overcast clouds* as a good video for blue-light
scattering. Check ACTUAL sampled 9:16 video pixels for visible blue sky in
scenes explicitly illustrating a blue daytime sky.

This is a visual color cue, never evidence that photons/molecules were filmed
or that a narrated scientific mechanism is true.
"""
from __future__ import annotations

import math
import re


_BLUE_SKY_TOPIC = re.compile(
    r"\bsky\b.{0,50}\bblue\b|\bblue\b.{0,50}\bsky\b"
    r"|\bhimmel\b.{0,50}\bblau\w*|\bblau\w*.{0,50}\bhimmel\b", re.I)
_BLUE_WORD = re.compile(r"\bblue\b|\bblau\w*\b", re.I)
_RELEVANT = re.compile(r"\bsky\b|\bsunlight\b|\bclouds?\b|\batmospher\w*\b"
                       r"|\bhimmel\b|\bsonnenlicht\b|\bwolken?\b", re.I)
_INTENTIONAL_CONTRAST = re.compile(
    r"\bsunsets?\b|\bsunrises?\b|\borange sky\b|\bred sky\b"
    r"|\bsonnenuntergang\b|\babendrot\b", re.I)


def requires_blue_sky_color(topic: str, narration: str, subject: str) -> bool:
    """Only blue-sky result/illustration scenes, not all nature or sunsets."""
    return bool(
        _BLUE_SKY_TOPIC.search(str(topic))
        and _BLUE_WORD.search(str(narration))
        and _RELEVANT.search(str(subject))
        and not _INTENTIONAL_CONTRAST.search(str(narration)))


def strong_blue_fraction(frame) -> float:
    """Count blue-dominant pixels on the final vertical crop.

    Resize to cap CPU cost. This heuristic is *not* a sky classifier: other
    metadata/CLIP/motion/license checks must already verify the sky subject.
    """
    image = frame.convert("RGB").resize((96, 168))
    data = image.tobytes()
    count = 0
    for i in range(0, len(data), 3):
        r, g, b = data[i:i+3]
        if (b > 50 and b > r * 1.18 and b > g * 1.07
                and b-r > 16 and b-g > 10):
            count += 1
    return count / (96 * 168)


def check_visible_blue_sky(path, duration, focus, *, frames=None):
    """Reject mostly-gray B-roll while preserving all strict video gates.

    Two of three sampled frames need substantial clearly blue area. No
    support is claimed for molecular scattering, wavelength, or causal truth.
    """
    if frames is None:
        if not math.isfinite(float(duration)) or float(duration) <= 0:
            raise ValueError("blue_sky_visual_invalid_duration")
        # Import lazily to avoid circular dependency with visual_director.
        from visual_director import _frame_at
        seconds = min(float(duration), 30.)
        timestamps = (
            min(.3, seconds*.1), seconds*.42, seconds*.77)
        frames = [_frame_at(path, t, focus) for t in timestamps]
    if len(frames) < 3:
        raise ValueError("blue_sky_visual_insufficient_frames")
    coverage = [strong_blue_fraction(im) for im in frames[:3]]
    passed = sum(value >= .48 for value in coverage) >= 2
    return {
        "verified": bool(passed),
        "blue_coverage": [round(value, 3) for value in coverage],
        "required_blue_fraction": 0.48,
        "required_frames": 2,
        "method": "sampled_final_portrait_crop_blue_color_cue",
        "limitations": "Color is not scientific proof or full semantic visual understanding",
    }
