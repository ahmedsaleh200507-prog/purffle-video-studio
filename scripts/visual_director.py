"""Evidence-first, shot-specific visual contracts for real-camera Shorts.

The director never makes up a video or claims a photo verifies a scientific
mechanism. It defines *visible* action/subject requirements from a completed,
independently fact-screened script. Real videos still need provider provenance,
native-resolution, motion, local CLIP, exact uniqueness and a successful render.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import io
import math
import re
import shutil
import subprocess
from pathlib import Path

from PIL import Image

from topic_footage import words

_SCENE_TARGET = ContextVar("purffle_director_scene_target", default=None)


@contextmanager
def use_story_scene_target(count):
    token = _SCENE_TARGET.set(count)
    try:
        yield
    finally:
        _SCENE_TARGET.reset(token)


def story_scene_target():
    return _SCENE_TARGET.get()


# Visualizable *actions*, not scientific truth claims. First spoken statement
# takes priority over later questions (lava flows / why explosions happen).
# These are reusable across subjects, not exception paths for individual jobs.
_EVENT_FAMILIES = (
    (
        "lava_flow", r"\b(lava|lavastrom|glühende lava)\b",
        ("lava flowing", "molten lava flow", "glowing lava close up"),
        "Real camera footage of bright red molten lava visibly flowing and moving.",
        "A static dark rocky mountain without moving molten lava.",
        ("lava", "molten", "eruption", "volcanic"),
    ),
    (
        "eruption", r"\b(erupt\w*|explos\w*|blast\w*|ash plume|ausbruch\w*|ausbrüch\w*|explodier\w*)\b",
        ("erupting ash plume", "explosive eruption", "eruption lava fountain"),
        "Real footage of an active volcanic eruption ejecting ash or a bright fountain of lava.",
        "A peaceful misty volcano mountain with clouds but no erupting ash or lava.",
        ("eruption", "erupt", "erupting", "ash", "plume", "explosion", "lava", "fountain"),
    ),
    (
        "breaching", r"\b(breach\w*|leap\w*|jump\w*|burst\w*\s+out|spring\w*|springen|springt|sprüng\w*)\b",
        ("breaching whale splash", "animal jumping water", "leaping animal"),
        "Real footage of a large sea animal visibly leaping above the water with a splash.",
        "A calm ocean surface or an animal swimming underwater without leaping.",
        ("breach", "breaching", "jump", "jumping", "leap", "leaping"),
    ),
    (
        "breaking", r"\b(break\w*\s+(?:into|apart|off)|fractur\w*|calv\w*|zerbrech\w*|abbrech\w*|abbricht)\b",
        ("iceberg breaking", "ice breaking apart", "glacier ice calving"),
        "Real video of a large piece of ice visibly splitting or breaking away into water.",
        "A stable motionless iceberg or glacier with no visible ice breaking.",
        ("break", "breaking", "calving", "fracture", "collapse", "iceberg"),
    ),
    (
        "lightning", r"\b(lightning|blitz\w*)\b",
        ("lightning strike storm", "lightning bolt sky", "thunderstorm lightning"),
        "Real video showing a visible lightning flash or bolt in a stormy sky.",
        "Only dark clouds and rain without a visible lightning flash.",
        ("lightning", "strike", "storm", "bolt", "blitz"),
    ),
    (
        "glowing", r"\b(glow\w*|bioluminescen\w*|leucht\w*)\b",
        ("glowing light", "glowing at night", "bioluminescent ocean"),
        "Real footage of the main subject visibly glowing or radiating light.",
        "A dark ordinary scene where the subject is not glowing.",
        ("glow", "glowing", "bioluminescent", "light", "shining"),
    ),
    (
        "water_motion", r"\b(wav\w*|welle\w*|surge\w*|splash\w*)\b",
        ("breaking waves", "ocean wave close up", "waves crashing"),
        "Real footage of large ocean waves visibly moving and breaking.",
        "A still flat sea without a visible moving wave.",
        ("wave", "waves", "surf", "splash", "ocean"),
    ),
)


def _scene_value(scene, field, default=""):
    if isinstance(scene, dict):
        return str(scene.get(field) or default)
    return str(getattr(scene, field, default) or default)


def _first_statement(narration):
    # A question at the end of a visual hook should not force an unshown
    # phenomenon into the opening shot (e.g. 'lava flows. Why does it explode?').
    return re.split(r"[.!?]", str(narration).strip(), maxsplit=1)[0]


def build_contract(scene, topic, index):
    """Prepare a bounded ordered search plan tied to THIS spoken scene."""
    narration = _scene_value(scene, "narration").strip()
    subject = _scene_value(scene, "object").strip()
    base = _scene_value(scene, "visual_search_query").strip()
    action = _scene_value(scene, "action").strip()
    if not narration or not subject or not base:
        raise ValueError("visual_director_missing_script_scene: narration/object/query")
    primary_clause = _first_statement(narration).casefold()
    chosen = None
    for name, pattern, variants, positive, negative, keywords in _EVENT_FAMILIES:
        # Verb alone is not enough: 'gas breaks magma apart' is NOT footage
        # of an iceberg cracking. Couple actions to the grounded visible
        # source subject rather than general English verb similarities.
        subject_lower = subject.casefold()
        relevant = (
            name == "lava_flow" and bool(re.search(r"volcan|lava|magma|vulkan", subject_lower))
            or name == "eruption" and bool(re.search(r"volcan|lava|magma|vulkan", subject_lower))
            or name == "breaching" and bool(re.search(r"whale|dolphin|wal|ocean", subject_lower))
            or name == "breaking" and bool(re.search(r"ice|glacier|iceberg|eis", subject_lower))
            or name == "lightning" and bool(re.search(r"lightning|blitz|storm", subject_lower))
            or name == "glowing" and bool(re.search(r"ocean|sea|aurora|northern|wave|polar|night|meer", subject_lower))
            or name == "water_motion" and bool(re.search(r"wave|ocean|sea|surf|welle|meer", subject_lower))
        )
        if relevant and re.search(pattern, primary_clause, re.I):
            chosen = (name, variants, positive, negative, keywords)
            break
    # For an invisible mechanism, stock footage is only an *illustration*.
    # Never insist on photons, gases inside magma or oxygen in lungs being
    # directly visible. Do not say illustrative video proves those mechanisms.
    illustrated = bool(re.search(
        r"\b(pressure|molecule|particle|gas|atom|force|weight|gravity|"
        r"oxygen|nitrogen|magnetic|electrons|sound|buoyancy|"
        r"druck|gase|sauerstoff|teilchen|magnetfeld)\b", primary_clause, re.I))
    if illustrated and chosen is None:
        event_required = False
    else:
        event_required = chosen is not None
    if chosen:
        family, variants, positive, negative, keywords = chosen
        # Use existing topic-anchored subject to keep synonyms factual. The
        # visual action is searchable, but the subject must remain visible.
        search = [f"{subject} {phrase}" for phrase in variants]
        if family == "lava_flow" and subject == "volcano":
            search = ["volcano glowing lava flow", "volcano lava flowing",
                      "molten lava close up"]
        elif family == "eruption" and subject == "volcano":
            search = ["volcano explosive eruption ash", "volcano eruption lava fountain",
                      "volcano erupting ash plume"]
        elif family == "breaching" and "whale" in subject:
            search = ["humpback whale breaching ocean", "whale jumping water",
                      "whale breaching splash"]
        elif family == "breaking" and "iceberg" in subject:
            search = ["iceberg breaking apart ocean", "iceberg calving sea",
                      "iceberg cracking apart"]
        elif family == "lightning":
            search = ["lightning bolt storm sky", "lightning striking clouds",
                      "thunderstorm lightning"]
        elif family == "glowing" and subject.casefold() in (
                "aurora", "northern lights", "polarlicht", "polarlichter",
                "nordlicht", "nordlichter"):
            # Production #89: the generic glowing family searched "aurora
            # bioluminescent ocean", exhausted the shot budget and missed
            # already available aurora footage. Keep EVERY query anchored to
            # the actual visible aurora rather than some other glowing object.
            search = ["aurora borealis", "northern lights timelapse",
                      "aurora night sky", "green northern lights"]
            positive = ("Real moving footage of luminous aurora borealis "
                        "curtains and bands glowing in the night sky.")
            negative = ("A sunset, unrelated glowing water or artificial "
                        "light without visible aurora curtains.")
            keywords = ("aurora", "borealis", "northern lights",
                        "polarlicht", "nordlicht", "glow", "glowing")
        elif family == "glowing" and "wave" in subject:
            search = ["bioluminescent ocean waves", "glowing ocean blue night",
                      "glowing plankton sea"]
        # Never overrule a visible action with the generic fallback, but allow
        # the primary stock query only when it contains the same event family.
        alternatives = search
        if any(token in base.casefold() for token in keywords):
            alternatives.append(base)
    else:
        family = "illustrative_subject"
        positive = ("A real moving documentary video with the "
                    f"{subject} clearly visible: {base}.")
        negative = (f"A generic empty background without the visible {subject}.")
        keywords = ()
        alternatives = [base]
        if action and action != "ambient":
            alternatives.append(f"{subject} {action}")
        if subject.casefold() not in base.casefold():
            alternatives.append(subject)
    unique, seen = [], set()
    for query in alternatives:
        query = re.sub(r"\s+", " ", str(query)).strip()[:95]
        if query and query.casefold() not in seen:
            seen.add(query.casefold())
            unique.append(query)
    if not unique:
        raise ValueError("visual_director_no_queries")
    return {
        "version": "evidence_first_shot_director_v1",
        "index": int(index),
        "subject": subject,
        "narration": narration,
        "family": family,
        "event_required": bool(event_required),
        "illustrative_science": bool(illustrated or not event_required),
        "queries": unique[:4],
        "positive": positive,
        "negative": negative,
        "metadata_keywords": list(keywords),
    }


def metadata_allows(contract, provider_text):
    """Necessary preflight, never a substitute for viewing source frames."""
    if not contract.get("event_required"):
        return True
    text = str(provider_text or "").casefold().replace("-", " ").replace("_", " ")
    clues = tuple(str(w) for w in contract.get("metadata_keywords", ()))
    # A negated mention ('ocean without lava') is evidence AGAINST the event,
    # not confirmation. This caught a false hit in the first v4 regression.
    if clues:
        disclaimed = r"\b(?:no|without|lacking|absence of|not showing)\s+(?:\w+\s+){0,2}(?:" + (
            "|".join(re.escape(w) for w in clues)) + r")\b"
        if re.search(disclaimed, text):
            return False
    # Explicit event vocabulary *and* scene-level visual CLIP are needed to
    # avoid explaining an eruption over an ordinary cloud-covered mountain.
    return any(re.search(r"(?<![a-z])" + re.escape(word), text)
               for word in clues)


def visual_scores(contract, scores, *, opening=False):
    """Generic event-vs-non-event ranking over the USED source-video interval.

    CLIP is a weak comparative heuristic: it cannot certify causal claims or
    identify a particular person. Fail closed rather than invent visual proof.
    """
    if not scores or any(not isinstance(row, (list, tuple)) or len(row) != 2 for row in scores):
        raise RuntimeError("visual_director_unverified_scores")
    scored = [float(row[0]) - float(row[1]) for row in scores]
    if any(not all(math.isfinite(float(x)) for x in row) for row in scores):
        raise RuntimeError("visual_director_unverified_scores")
    peak = max(float(row[0]) for row in scores)
    margin = max(scored)
    # A single middle/late frame can reveal the exact physical action, while
    # an opening frame may show the buildup. Thresholds are conservative
    # editorial heuristics, not measured accuracy or viewer-retention scores.
    passed = peak >= 0.24 and margin >= 0.02
    # On scene 1 a late event cannot rescue a sky-only or dormant first
    # three seconds. First two timestamps are within roughly 0-2s.
    opening_action_visible = None
    if opening and contract["event_required"]:
        opening_action_visible = any(
            float(row[0]) >= 0.24 and float(row[0]) - float(row[1]) >= 0.02
            for row in scores[:2])
        passed = passed and opening_action_visible
    return {
        "verified": bool(passed),
        "opening_action_visible": opening_action_visible,
        "family": contract["family"],
        "event_required": bool(contract["event_required"]),
        "max_similarity": round(peak, 4),
        "best_action_margin": round(margin, 4),
        "sampled_scene_frames": len(scores),
        "method": "multi_timestamp_portrait_clip_action_vs_inactive_scene",
        "limitations": "Does not prove causal process or audience retention",
    }


def _frame_at(path, seconds, crop_focus, *, runner=None):
    runner = runner or subprocess.run
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("visual_director_ffmpeg_unavailable")
    focus = float(crop_focus)
    if not math.isfinite(focus) or not 0 <= focus <= 1:
        raise RuntimeError("visual_director_invalid_crop")
    expression = ("scale=192:340:force_original_aspect_ratio=increase,"
                  "crop=192:340:x='max(0,min(iw-ow,iw*"
                  f"{focus:.5f}" + "-ow/2))':y='(ih-oh)/2',setsar=1")
    process = runner(
        [ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error",
         "-ss", str(max(0., seconds)), "-i", str(Path(path)),
         "-vf", expression, "-frames:v", "1",
         "-f", "image2pipe", "-vcodec", "mjpeg", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        timeout=8, check=False)
    if process.returncode or not process.stdout:
        raise RuntimeError("visual_director_frame_unavailable")
    with Image.open(io.BytesIO(process.stdout)) as img:
        return img.convert("RGB").copy()


def inspect_action(path, duration, crop_focus, contract, *,
                   scorer=None, frames=None, opening=False):
    """Check the ACTUAL rendered interval (not the whole stock source clip)."""
    if frames is None:
        length = float(duration)
        if not math.isfinite(length) or length <= 0:
            raise RuntimeError("visual_director_missing_duration")
        # The renderer uses item.extra['start']=0 and only the first NEED
        # seconds. Inspecting the entire source would approve an explosion
        # at 40s even when the final video cuts away at 10s.
        times = [min(.4, length * .1), min(1.7, length * .35), length * .66]
        frames = [_frame_at(path, moment, crop_focus) for moment in times]
    if not frames or len(frames) < 2:
        raise RuntimeError("visual_director_unverified_frames")
    if scorer is None:
        from media_validation import SceneMatcher
        scorer = SceneMatcher()._similarities
    matrix = scorer(frames, [contract["positive"], contract["negative"]])
    return visual_scores(contract, matrix, opening=opening)



def verify_visible_event_or_illustrative_subject(
        path, duration, crop_focus, contract, matched_scene, *,
        scorer=None, opening=False, event_inspector=None):
    """Independently verified subject footage need not depict a fictional action.

    A context shot of real ocean waves may validly illustrate invisible wind
    dynamics without proving one precise event. The preceding SceneMatcher
    must still verify the actual topic subject in real frames, provider
    metadata, and portrait crop; QualityValidator separately verifies moving
    video and native HD. Event-required speech keeps every prior strict
    multi-frame action check, including the first 2 seconds of its hook.
    """
    if not isinstance(matched_scene, dict) or (
            matched_scene.get("verification") != "local_clip_screening"):
        raise RuntimeError("visual_director_missing_independent_clip_match")
    if not contract.get("event_required"):
        return {
            "verified": True,
            "event_required": False,
            "family": contract["family"],
            "opening_action_visible": None,
            "method": "local_clip_subject_match_no_specific_event_claim",
            "limitations": (
                "Subject-relevant real video, not proof of a narrated "
                "invisible mechanism or unshown action."),
        }
    inspect = event_inspector or inspect_action
    result = inspect(
        path, duration, crop_focus, contract, scorer=scorer, opening=opening)
    if not result.get("verified"):
        raise ValueError(
            "visual_director_action_not_visible: real 9:16 frames do not "
            "demonstrate " + str(contract["family"]))
    return result
