"""Purffle's topic-adaptive four-phase storytelling standard.

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


def choose_duration_seconds(topic: str, scene_count: int, *, fact_count: int = 0) -> int:
    """Choose an editorial LENGTH TARGET from topic and grounded material.

    It is not a speech hard-stop. Actual duration is determined by real
    narration, and no filler or looping is ever permitted to meet the target.
    """
    if not 2 <= scene_count <= 6:
        raise ValueError("Full Shorts duration needs 2–6 verified real scenes")
    terms = _words(topic)
    complexity = min(6, len(terms) // 3)
    evidence_depth = min(8, max(0, fact_count - 2) * 2)
    # More available verified scenes and more evidence permit a longer story.
    # Short single-mechanism topics should naturally get a shorter plan.
    return min(55, max(16, round(scene_count * 6.25 + complexity + evidence_depth)))


def editorial_phase_windows(seconds: float = STANDARD_SECONDS) -> list[dict]:
    """Scale storytelling BEATS, keeping the crucial first-second hook short.

    There are no fixed cuts: the MP4 may last 18, 25, 38, 45 seconds, etc.
    A viewer's behavior is measured only in YouTube Studio, not by this plan.
    """
    seconds = float(seconds)
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("Video duration must be positive and finite")
    hook_end = min(2.0, seconds * .2)
    curiosity_end = max(hook_end, seconds * 8 / 30)
    development_end = max(curiosity_end, seconds * 22 / 30)
    edges = (0, hook_end, curiosity_end, development_end, seconds)
    return [
        {"name": name, "start_seconds": round(edges[i], 2),
         "end_seconds": round(edges[i+1], 2), "goal": purpose}
        for i, (name, _begin, _end, purpose) in enumerate(PHASES)
    ]


def storyboard_writer_brief(scene_count: int, planned_seconds: int | None = None) -> str:
    if not 1 <= scene_count <= 6:
        raise ValueError("Retentive Shorts require 1 to 6 real scenes")
    proposed = planned_seconds if planned_seconds is not None else (
        choose_duration_seconds("educational documentary", scene_count)
        if scene_count >= 2 else 12)
    beats = editorial_phase_windows(proposed)
    from editorial_standard import CORE_BRIEF
    return (
        CORE_BRIEF + " " +
        "MANDATORY FLEXIBLE FOUR-PHASE SHORTS STORY STRUCTURE. "
        "The topic and validated facts determine the length: NO mandatory "
        "30-second runtime, and no filler to match a target. "
        f"Planned narrative length approx {proposed} seconds, adjustable "
        "if the true explanation needs fewer words. "
        "0–2s HOOK — FIRST 1–2 SECONDS ARE MOST IMPORTANT: Start with the "
        "strongest ACTUALLY VERIFIED real moving footage and a SHORT, vivid, "
        "specific true spoken opening. No title card, no silence, no greeting, "
        "no repeated full video title, no unrelated shot. "
        f"CURIOSITY — by around {beats[1]['end_seconds']}s give the "
        "first meaningful fact without delaying the answer. "
        f"DEVELOPMENT — until around {beats[2]['end_seconds']}s, "
        "advance the subject-specific story with fresh supported evidence, events, facts or insights and genuinely relevant shots. "
        "PAYOFF — in the remaining final segment, answer clearly and "
        "finish on a meaningful image, with no CTA or fake cliffhanger. "
        f"You have {scene_count} verified shots, not necessarily four beats "
        "mapped one-to-one onto four shots. "
        "A 1-shot preview has all four beats in one shot. "
        "With three shots, hook and curiosity share the first shot; "
        "later shots advance and resolve the question. "
        "Prefer short natural spoken sentences, simple explanations of technical terms, and meaningful visual changes as the story progresses. When evidence and available footage support it, use three to six distinct shots, normally around three to seven seconds each; allow longer shots for a meaningful continuous event and fewer shots when appropriate. Do not cut merely to satisfy a timer. "
        "Do not loop footage or stretch narration to a specified length. "
        "Write a UNIQUE source-grounded narrative for THIS topic, "
        "avoid interchangeable or repetitive mass-produced shock-bait, "
        "and retain the independent facts and footage review."
    )


def audit_storyboard(topic: str, screenplay, language="en", *, scenes=None, planned_seconds=None) -> dict:
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
    from editorial_standard import enabled, audit_structure
    shared=audit_structure(texts,language,mode="short") if enabled() else None
    return {
        "shared_editorial_standard":shared,
        "state": "editorial_screen_passed",
        "version": "shorts_four_phase_adaptive_v2",
        "duration_policy": "topic_and_verified_footage_adaptive_not_fixed",
        "planned_duration_seconds": planned_seconds,
        "example_reference_seconds": STANDARD_SECONDS,
        "phases": editorial_phase_windows(planned_seconds or STANDARD_SECONDS),
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


def validate_short_duration(actual_seconds, planned_seconds=None):
    """Do not classify an undersized or padded export as a completed Short."""
    actual=float(actual_seconds)
    if not math.isfinite(actual) or not 16.0<=actual<=60.0:
        raise RuntimeError("short_duration_invalid: expected 16–60 seconds of genuine narration and footage")
    if planned_seconds is not None:
        planned=float(planned_seconds)
        if not math.isfinite(planned) or planned<=0:
            raise ValueError("Invalid editorial duration target")
        if actual < planned*.75:
            raise RuntimeError("short_duration_invalid: export below 75 percent of planned duration")
    return actual
