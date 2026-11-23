"""Publication quality contract for long documentaries.

A file that is 10 minutes long is NOT a 10-minute documentary if the
narrator speaks for one minute, facts repeat or the clip has no real footage.
The previous 2D failsafe repeated 7 sentences and padded each 4-second
sentence to a 43-second chapter. Reject that before any expensive render.

A true documentary must have ~10 minutes of ORIGINAL spoken material, moving
subject-matched footage and no long blocks of silence.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path


class DocumentaryQualityError(RuntimeError):
    pass


def verify_narration(chapters, language: str = "en") -> dict:
    if not isinstance(chapters, list) or len(chapters) != 14:
        raise DocumentaryQualityError("long_requires_14_substantive_chapters")
    utterances = []
    titles = []
    counts = []
    for i, c in enumerate(chapters):
        if not isinstance(c, dict):
            raise DocumentaryQualityError(f"chapter_{i+1}_not_an_object")
        line = " ".join(str(c.get("narration", "")).split())
        title = " ".join(str(c.get("title", "")).split()).casefold()
        words = re.findall(r"\b[\wÄÖÜäöüß'-]+\b", line, re.UNICODE)
        if len(words) < 80:
            raise DocumentaryQualityError(
                f"chapter_{i+1}_has_only_{len(words)}_spoken_words")
        utterances.append(" ".join(words).casefold())
        titles.append(title)
        counts.append(len(words))
    if len(set(utterances)) != len(utterances):
        raise DocumentaryQualityError("long_repeated_narration_chapters")
    if len(set(titles)) != 14:
        raise DocumentaryQualityError("long_repeated_chapter_titles")
    # Protect against near-duplicate chapters with only changed intro text.
    # Small common 5-grams are normal; a large overlap is not.
    for i in range(14):
        tokens = utterances[i].split()
        a = {" ".join(tokens[x:x+7]) for x in range(len(tokens)-6)}
        for j in range(i):
            other = utterances[j].split()
            b = {" ".join(other[x:x+7]) for x in range(len(other)-6)}
            overlap = len(a & b) / max(1, min(len(a), len(b)))
            if overlap > .32:
                raise DocumentaryQualityError(
                    f"long_repetitive_chapters_{j+1}_and_{i+1}")
    total = sum(counts)
    if total < 1200:
        raise DocumentaryQualityError(
            f"long_only_{total}_spoken_words_need_at_least_1200")
    return {"chapters":len(chapters),"spoken_words":total,
            "minimum_chapter_words":min(counts),
            "narration_not_repeated":True}


def verify_finished(video, chapters, credits, *, language="en") -> dict:
    proof = verify_narration(chapters, language)
    if not isinstance(credits, list):
        raise DocumentaryQualityError("long_real_footage_credits_missing")
    verified = [c for c in credits if isinstance(c, dict)
                and c.get("visual_check") == "local_clip_screening"
                and c.get("source") and c.get("id") is not None]
    unique = {(c["source"], str(c["id"])) for c in verified}
    if len(verified) < 14 or len(unique) < 10:
        raise DocumentaryQualityError(
            f"long_insufficient_real_video_variety_verified={len(verified)}"
            f"_unique={len(unique)}")
    # Check for any >5s spans of true audio silence. SRT/word count above
    # makes continuous background music alone insufficient to pass.
    try:
        result = subprocess.run([
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "info",
            "-i", str(Path(video)), "-vn",
            "-af", "silencedetect=noise=-35dB:d=5", "-f", "null", "-"
        ], capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DocumentaryQualityError(
            "long_audio_silence_validation_unavailable") from exc
    if result.returncode:
        raise DocumentaryQualityError("long_audio_silence_validation_failed")
    if "silence_start:" in result.stderr:
        raise DocumentaryQualityError(
            "long_contains_silent_gap_of_5_seconds_or_more")
    return {**proof, "unique_verified_source_videos":len(unique),
            "verified_clip_uses":len(verified),
            "long_silence_gaps_over_5_seconds":0,
            "publication_quality":"narrated_real_footage_validated"}
