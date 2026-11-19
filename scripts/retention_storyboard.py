"""Purffle's default 30-second, four-phase editorial standard.

The structure is based on the *story*, not four artificially equal video clips.
For 3-4 verified camera shots, the first clip contains hook + curiosity;
later clips supply real facts and a payoff. It never weakens science, source,
license, voice, motion, speaker or caption checks.

YouTube audience retention and monetization can only be judged by actual
channel metrics and platform review; this report does NOT certify either.
"""
from __future__ import annotations

from difflib import SequenceMatcher
import json
import math
from pathlib import Path
import re


STANDARD_SECONDS = 30
PHASES = (
    ("hook", 0, 2, "Striking verified footage + an immediate concrete opening"),
    ("curiosity", 2, 8, "First useful fact and natural unanswered question"),
    ("development", 8, 22, "Fresh facts, relevant shots, no repetition or filler"),
    ("payoff", 22, 30, "Complete factual answer with satisfying visual ending"),
)

_EN_INTROS = (
    "welcome", "hello everyone", "hey guys", "hi everyone",
    "in this video", "today we will", "today we're", "did you know",
    "let me tell you", "have you ever wondered", "before we begin",
)
_DE_INTROS = (
    "willkommen", "hallo zusammen", "in diesem video", "heute zeigen wir",
    "heute werden wir", "wusstest du", "bevor wir anfangen",
)
_BAD_ENDINGS = (
    "like and subscribe", "subscribe to", "hit the bell",
    "follow for more", "comment below", "share this video",
    "stay tuned", "watch part two", "don't forget to like",
    "like das video", "abonniere", "kommentiere unten",
    "folgt mir", "vergesst nicht zu abonnieren",
)


def _words(text: str) -> list[str]:
    return re.findall(r"[^\W_]+(?:['’][^\W_]+)?", str(text).casefold(), flags=re.UNICODE)


def editorial_phase_windows(seconds: float = STANDARD_SECONDS) -> list[dict]:
    """Scale the example 30-second plan when actual audio has a different length.

    These are *editorial targets*, not a claim the real MP4's speech was
    separately timestamped or that viewers watched those seconds.
    """
    seconds = float(seconds)
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("Video duration must be positive and finite")
    return [
        {"name": name, "start_seconds": round(seconds * begin / 30, 2),
         "end_seconds": round(seconds * end / 30, 2), "goal": purpose}
        for name, begin, end, purpose in PHASES
    ]


def storyboard_writer_brief(scene_count: int) -> str:
    if not 1 <= scene_count <= 6:
        raise ValueError("Retentive Shorts require 1 to 6 real scenes")
    return (
        "MANDATORY FOUR-PHASE 30-SECOND SHORTS STORY STRUCTURE: "
        "0–2s HOOK — within the very first spoken words, show the most vivid "
        "actually VERIFIED real camera footage and describe an interesting "
        "concrete, truthful observation. NO huge title overlay, no generic "
        "greeting and no full question repeated from the YouTube title. "
        "2–8s CURIOSITY — add a first meaningful scientific fact immediately "
        "and establish why the outcome is surprising; do not delay the "
        "entire answer until the end. "
        "8–22s DEVELOPMENT — reveal different mechanisms, contrasts or "
        "consequences supported by science and the actual shots; every "
        "scene adds new, specific information. "
        "22–30s PAYOFF — clearly answer the video's original question "
        "and finish with a relevant real visual, NOT a subscribe/comment CTA. "
        f"You have {scene_count} verified shots, not necessarily four shots. "
        "In a rare 1-shot preview, carry all four phases in the one clip. "
        "In a 3-shot version, scene one contains hook+curiosity, scene two "
        "develops, scene three answers. In a 4-shot version, the first "
        "shot still carries the first 0–8s and the others progress and pay off. "
        "The 30 seconds are editorial guides, not fixed audio timestamps. "
        "Do not pad the script or loop short footage simply to reach 30s. "
        "Write a UNIQUE source-grounded explanation of this specific topic; "
        "avoid interchangeable generic lines and mass-produced shock-bait. "
        "Every scientific and causal claim must pass the existing source "
        "review, and the visuals must not misrepresent real events."
    )


def audit_storyboard(topic: str, screenplay, language="en", *, scenes=None) -> dict:
    """Reject obviously weak templated intros and spam *before* narrator TTS.

    This simple deterministic editorial check complements, but never replaces,
    the independent factual and visual model checks. It is NOT a prediction
    of audience retention or YouTube monetization eligibility.
    """
    source = scenes if scenes is not None else getattr(screenplay, "scenes", ())
    texts = [
        str(scene["narration"] if isinstance(scene, dict) else getattr(scene, "narration", "")).strip()
        for scene in source
    ]
    if not 2 <= len(texts) <= 6 or any(len(_words(t)) < 5 for t in texts):
        raise RuntimeError("retention_storyboard_invalid: scenes missing or too short")
    opening = texts[0].casefold()
    first_phrase = " ".join(_words(opening)[:8])
    intros = _DE_INTROS if str(language).startswith("de") else _EN_INTROS
    if any(opening.startswith(intro) for intro in intros):
        raise RuntimeError("retention_storyboard_invalid: generic intro before useful hook")
    if any(term in " ".join(texts).casefold() for term in _BAD_ENDINGS):
        raise RuntimeError("retention_storyboard_invalid: generic engagement CTA")
    # The opening must not simply read the video's existing question aloud.
    topic_tokens, hook_tokens = _words(topic), _words(texts[0])
    if (topic_tokens and len(hook_tokens) > 5
            and topic_tokens == hook_tokens[:len(topic_tokens)]):
        raise RuntimeError("retention_storyboard_invalid: full title repeated as intro")
    for one, two in zip(texts, texts[1:]):
        if SequenceMatcher(None, _words(one), _words(two)).ratio() >= .88:
            raise RuntimeError("retention_storyboard_invalid: repeated scene narration")
    if len(_words(texts[-1])) < 7:
        raise RuntimeError("retention_storyboard_invalid: no substantive final answer")
    return {
        "state": "editorial_screen_passed",
        "version": "shorts_four_phase_v1",
        "template_target_seconds": STANDARD_SECONDS,
        "phases": editorial_phase_windows(),
        "scene_count": len(texts),
        "language": str(language)[:2],
        "first_spoken_words": " ".join(_words(texts[0])[:7]),
        "last_scene_word_count": len(_words(texts[-1])),
        "narration_word_count": sum(map(lambda x: len(_words(x)), texts)),
        "originality_notes": [
            "Unique question-specific educational narration required",
            "Source licensing and truthful interpretation required",
            "Mass-produced video templates are not monetization-certified",
            "No fake views or misleading retention statistics",
        ],
        "scope": "Script structure checked, not an audience-retention guarantee",
    }


def save_storyboard_report(filename, audit: dict, *, duration_seconds=None):
    result = dict(audit)
    if duration_seconds is not None:
        seconds = float(duration_seconds)
        if not math.isfinite(seconds) or seconds <= 0:
            raise ValueError("Invalid real MP4 duration")
        result["actual_video_duration_seconds"] = round(seconds, 2)
        result["editorial_phase_targets_scaled_to_video"] = editorial_phase_windows(seconds)
        result["warning"] = (
            "Time ranges are target editorial windows; only YouTube Studio "
            "can measure actual viewer retention and monetization."
        )
    p = Path(filename)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return p
