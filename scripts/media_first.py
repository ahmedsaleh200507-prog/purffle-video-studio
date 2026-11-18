"""Purffle V3: verify real topic-related footage BEFORE writing or voicing.

Nothing in this module fabricates a clip or claims metadata alone is verification.
A preselected MediaItem is reused directly in the existing upstream renderer,
avoiding scene-by-scene re-search after the speech has already been produced.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import time

_CURRENT = ContextVar("purffle_media_first", default=None)


@dataclass
class VerifiedPalette:
    topic: str
    plans: list[dict]
    items: list[object]
    credits: set[str]
    attempts: list[dict]

    @property
    def media_map(self):
        # Upstream Studio.produce() supports a media_map keyed by (scene,part).
        # Its max_shot_seconds=0 config yields one part per scene.
        return {(index, 0): clip for index, clip in enumerate(self.items)}


def active_palette():
    return _CURRENT.get()


@contextmanager
def use_palette(palette):
    token = _CURRENT.set(palette)
    try:
        yield
    finally:
        _CURRENT.reset(token)


def _grounded_candidates(topic, llm=None):
    """Prepare a *palette*, not a fake storyboard of unfilmable events."""
    from studio_runtime import thematic_scene_plans
    template = dict(main_character="", object="topic",
                    action="ambient", location="", time="",
                    visual_search_query="topic")
    curated = thematic_scene_plans(template, topic)
    # Ask for extra stock-query vocabulary even for recognized subjects.
    # Otherwise one provider outage can exhaust the only four known queries.
    # These remain candidate queries: only actually downloaded, inspected,
    # licensed, moving clips can ever enter the validated palette.
    # New, unrecognised subjects get one inexpensive visual vocabulary query
    # to the existing free Groq LLM; narration is NOT requested at this point.
    if llm is None:
        return curated
    schema = {
        "type": "object",
        "properties": {"shots": {"type": "array", "minItems": 5, "maxItems": 9,
            "items": {"type": "object",
                      "properties": {
                          "object": {"type": "string"},
                          "query": {"type": "string"},
                      }, "required": ["object", "query"],
                      "additionalProperties": False}}},
        "required": ["shots"], "additionalProperties": False,
    }
    system = ("You plan truthful *real camera stock footage*, not narration. "
              "Suggest common filmable, topic-related visual subjects only. "
              "No precise historical reenactments, imaginary measurements, "
              "photographs of impossible events, fictional people, diagrams, "
              "titles on screens or artificial footage. Reply only with JSON.")
    prompt = (f"VIDEO TOPIC: {topic}\n"
              "List 7-9 diverse, directly filmable B-roll possibilities. "
              "Each object must be a visible noun of one or two words. "
              "Query must be 2-5 ordinary English stock-video search words. "
              "All imagery must plausibly support the topic without implying "
              "it literally shows an event or an invisible scientific process.")
    try:
        data = llm.complete_json(system, prompt, schema)
    except Exception as exc:
        print(f"[MEDIA FIRST] palette model unavailable: {type(exc).__name__}", flush=True)
        return curated
    if not isinstance(data, dict) or not isinstance(data.get("shots"), list):
        return curated
    seen = {x["visual_search_query"].lower() for x in curated}
    allowed_objects = {x["object"].casefold() for x in curated}
    topic_words = {x.casefold().rstrip("s") for x in re.findall(r"[a-z]{4,}", topic)
                   if x.casefold() not in {"what", "when", "where", "which",
                   "does", "would", "happen", "really", "again", "from",
                   "with", "that", "this", "your", "have", "into", "there",
                   "many", "some", "world", "most", "ever", "more", "same"}}
    for raw in data.get("shots", [])[:9]:
        if not isinstance(raw, dict):
            continue
        obj = str(raw.get("object") or "").strip()[:60]
        query = re.sub(r"\s+", " ", str(raw.get("query") or "")).strip()[:100]
        if (not obj or not query or not (1 <= len(obj.split()) <= 3)
                or not (2 <= len(query.split()) <= 6) or query.lower() in seen
                or any(x in query.lower() for x in ("animation", "simulation",
                              "infographic", "reenactment", "rendering"))):
            continue
        # Don't let the visual-planning LLM pivot a science documentary to
        # unrelated footage. For known topics only extend the same visible
        # subject families; for unknown topics require a topic-noun overlap.
        query_words = {x.casefold().rstrip("s") for x in re.findall(r"[a-z]{4,}",
                         obj + " " + query)}
        if curated and not (obj.casefold() in allowed_objects or
                            any(x in query_words for x in allowed_objects)):
            continue
        if not curated and topic_words and not (query_words & topic_words):
            continue
        seen.add(query.lower())
        curated.append(dict(main_character="", object=obj, action="ambient",
                            location="", time="", visual_search_query=query))
    return curated


def prepare_verified_palette(topic, settings, llm=None, *, visuals=None,
                             min_scenes=3, max_scenes=4, clip_seconds=10.0):
    """Download, probe, and visually verify each potential shot BEFORE TTS.

    On failure there is an early, explicit media-preflight error rather than a
    perfectly narrated video that cannot be rendered. All clips use the same
    StrictVisuals per-scene validation gates as the old pipeline.
    """
    from studio_runtime import StrictVisuals, _scene_data
    if not topic or not str(topic).strip():
        raise ValueError("Media-first preflight requires the requested video topic")
    if not (2 <= min_scenes <= max_scenes <= 6):
        raise ValueError("Media-first scene limits must be 2..6")
    if clip_seconds <= 0:
        raise ValueError("Media-first clip length must be positive")
    visuals = visuals if visuals is not None else StrictVisuals(settings)
    options = _grounded_candidates(topic, llm)
    if not options:
        raise RuntimeError("media_preflight_no_topic_palette: cannot find filmable subject suggestions")
    items, plans, attempts, selected_rows = [], [], [], []
    dest_dir = Path(os.environ.get("MEDIA_FIRST_WORK_DIR", "media_cache/v3_preflight"))
    dest_dir.mkdir(parents=True, exist_ok=True)
    for option in options:
        if len(items) == max_scenes:
            break
        plan = _scene_data(option)
        query = plan["visual_search_query"]
        # Keep a bounded total selection budget even with many providers.
        visuals._shot_deadline = time.monotonic() + 135
        start = len(visuals.report["scenes"])
        try:
            item = visuals.for_scene(len(items), query, json.dumps(plan),
                                     topic, clip_seconds, dest_dir)
        except RuntimeError as exc:
            if "No suitable verified REAL VIDEO" not in str(exc):
                raise
            attempts.append({"query": query, "status": "rejected",
                             "reason": str(exc)[:220]})
            continue
        matches = [row for row in visuals.report["scenes"][start:]
                   if row.get("status") == "selected"]
        if len(matches) != 1:
            raise RuntimeError("media_preflight_inconsistent_scene_selection")
        selected_rows.append(matches[0])
        items.append(item)
        plans.append(plan)
        attempts.append({"query": query, "status": "selected",
                         "source": item.source, "id": item.id})
    # Re-number successful selections because rejected candidates occupied
    # transient scene indexes. Never mistake skipped attempts for final scenes.
    for index, row in enumerate(selected_rows, 1):
        row["index"] = index
        row["visual_mode"] = "media_first_verified"
        row["illustrative_not_exact_event"] = True
    visuals.report["scenes"] = selected_rows
    visuals.report["state"] = "footage_ready" if len(items) >= min_scenes else "failed"
    visuals.report["strategy"] = "v3_media_first_verified_before_script_and_voice"
    visuals.report["preflight_attempts"] = attempts
    if len(items) < min_scenes:
        visuals.report["error"] = (
            f"media_preflight_insufficient_footage: verified {len(items)} "
            f"of {min_scenes} required unique video clips")
    else:
        visuals.report.pop("error", None)
    visuals._save()
    save_path = Path(os.getenv("MEDIA_FIRST_REPORT", "media-first-plan.json"))
    save_path.parent.mkdir(parents=True, exist_ok=True)
    save_path.write_text(json.dumps({
        "strategy": "v3_media_first_verified_before_script_and_voice",
        "topic": topic, "required": min_scenes, "verified": len(items),
        "selected": [
            {"index": i+1, "query": p["visual_search_query"],
             "object": p["object"], "source": m.source, "id": m.id,
             "sha256": m.extra.get("sha256"),
             "quality": m.extra.get("quality"),
             "license": m.extra.get("license")}
            for i, (p, m) in enumerate(zip(plans, items))],
        "attempts": attempts,
    }, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    if len(items) < min_scenes:
        raise RuntimeError(visuals.report["error"])
    print(f"[MEDIA FIRST] {len(items)} verified clips ready BEFORE script or voice", flush=True)
    return VerifiedPalette(str(topic), plans, items, visuals.credits.copy(), attempts)


def footage_prompt(palette) -> str:
    """Footage evidence for the scriptwriter (not a claim of event accuracy)."""
    lines = [
        "MEDIA-FIRST VERIFIED SHOTS. These clips are ALREADY obtained, measured, "
        "licensed and visually screened. The narration must be grounded in the "
        "topic; do not invent specific facts just to fit a picture.",
        f"Write EXACTLY {len(palette.plans)} scenes in this order. "
        "Each scene corresponds to the indicated real footage. "
        "Do NOT request new shots or more scenes. Write 12-19 spoken words "
        "per scene; concise lines ensure the audio fits each unlooped clip.",
        "Every scene MUST remain scientifically truthful, without fake places, "
        "experiments, witnesses, exact measurements or dramatic invented facts. "
        "The image illustrates the subject; it is not a recording of the exact event.",
    ]
    for index, (plan, clip) in enumerate(zip(palette.plans, palette.items), 1):
        duration = float(getattr(clip, "duration", 12) or 12)
        max_words = max(10, min(21, int((duration - 1.5) * 2.0)))
        lines.append(f"SCENE {index}: verified real B-roll of {plan['object']} "
                     f"(stock query: {plan['visual_search_query']}). "
                     f"Use visual_search_query exactly: {plan['visual_search_query']}. "
                     f"Narration maximum {max_words} words to fit this "
                     f"{duration:.1f}-second unlooped clip.")
    return "\n".join(lines)


def _fit_scene_count(raw_scenes, size):
    """Merge surplus lines without losing narration; never invent missing lines."""
    scenes = [dict(x) for x in raw_scenes if isinstance(x, dict)
              and str(x.get("narration", "")).strip()]
    if not scenes:
        raise ValueError("media_first_script_mismatch: LLM produced no narration")
    # If the model under-produces scenes, split an existing long line into
    # contiguous spoken segments. This preserves ALL original words and facts
    # without inventing commentary or discarding a verified clip.
    while len(scenes) < size:
        index = max(range(len(scenes)),
                    key=lambda i: len(scenes[i]["narration"].split()))
        words = scenes[index]["narration"].split()
        if len(words) < 8:
            raise ValueError("media_first_script_mismatch: insufficient narration to split")
        mid = len(words) // 2
        first = dict(scenes[index], narration=" ".join(words[:mid]))
        second = dict(scenes[index], narration=" ".join(words[mid:]))
        scenes[index:index+1] = [first, second]
    while len(scenes) > size:
        tail = scenes.pop()
        scenes[-1]["narration"] = (
            str(scenes[-1]["narration"]).rstrip() + " " +
            str(tail.get("narration", "")).strip()).strip()
    return scenes


def validate_narration_timing(palette, script, language="en"):
    """Catch source-too-short errors before TTS and render, using a conservative
    speech-rate estimate. Real TTS timing is still validated by the renderer.
    """
    if not palette:
        return
    if len(script.scenes) != len(palette.items):
        raise RuntimeError("media_first_script_mismatch: scene count differs from validated clips")
    words_per_sec = 2.0 if str(language).startswith("de") else 2.25
    for index, (scene, item) in enumerate(zip(script.scenes, palette.items), 1):
        words = len(re.findall(r"\b[\w'-]+\b", scene.narration))
        duration = float(getattr(item, "duration", 0) or 0)
        estimate = words / words_per_sec + 1.2
        if duration < estimate:
            raise RuntimeError(
                f"media_first_narration_too_long: scene {index} "
                f"estimated {estimate:.1f}s of speech for {duration:.1f}s of verified footage")


def align_script_to_palette(data, palette):
    """Never let an LLM invent a new visual plan after footage was obtained."""
    if not palette:
        return data
    scenes = _fit_scene_count(data.get("scenes") or [], len(palette.plans))
    for scene, plan in zip(scenes, palette.plans):
        scene.update(plan)
        scene["search_query"] = plan["visual_search_query"]
        scene["image_prompt"] = ""
    return {**data, "scenes": scenes}
