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

from topic_footage import (deterministic_stock_shots, related_to_topic,
                           subject_terms, words, is_lava_ocean_topic,
                           lava_subject_in_metadata)

_CURRENT = ContextVar("purffle_media_first", default=None)


@dataclass
class VerifiedPalette:
    topic: str
    plans: list[dict]
    items: list[object]
    credits: set[str]
    attempts: list[dict]
    planned_seconds: int | None = None

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
    # Stock-first search must work even for topics not yet in the curated
    # mapping. The fallback is derived from the topic, not a hallucinated event.
    seeds = deterministic_stock_shots(topic)
    seen_seed = set()
    # Preserve existing proven subject ranking for already curated topics;
    # hurricane footage needs actual cyclone-first establishing shots.
    from topic_footage import is_steel_ship_floating_topic, is_glowing_ocean_topic
    prioritized = (
        seeds + curated
        if "hurricane" in topic.casefold()
        or is_steel_ship_floating_topic(topic)
        or is_glowing_ocean_topic(topic)
        or bool(words(topic) & {"shark", "whale", "volcano", "meteor", "iceberg"})
        else curated + seeds
    )
    curated = [plan for plan in prioritized
               if not (plan["visual_search_query"].lower() in seen_seed
                       or seen_seed.add(plan["visual_search_query"].lower()))]
    if seeds:
        # Prevent unrelated pre-curated B-roll from being mistaken for an
        # authoritative causal event. #71 selected 'lightning storm' for
        # volcanic-island formation, then the LLM invented a story that
        # lightning formed fissures. Source footage must relate to actual
        # topic terms, not just coexist in an older generic fallback family.
        rejected = [p["visual_search_query"] for p in curated
                    if not related_to_topic(
                        topic, p["object"], p["visual_search_query"])]
        curated = [p for p in curated if related_to_topic(
            topic, p["object"], p["visual_search_query"])]
        if rejected:
            print("[MEDIA FIRST] Off-topic stock queries removed: " +
                  ", ".join(rejected[:8]), flush=True)
    # Ask for extra stock-query vocabulary even for recognized subjects.
    # Otherwise one provider outage can exhaust the only four known queries.
    # These remain candidate queries: only actually downloaded, inspected,
    # licensed, moving clips can ever enter the validated palette.
    # New, unrecognised subjects get one inexpensive visual vocabulary query
    # to the existing free Groq LLM; narration is NOT requested at this point.
    if is_lava_ocean_topic(topic):
        # The #77 regression: LLM/generic ocean fallbacks contained no lava.
        # Keep the search concrete and require actual lava/volcano tags.
        # If genuine footage cannot be verified, reject before TTS.
        return [p for p in curated
                if lava_subject_in_metadata(p["visual_search_query"])]
    if is_glowing_ocean_topic(topic):
        # Explicit bioluminescence metadata is mandatory; attractive normal
        # water footage must not substitute for real visible blue plankton.
        from topic_footage import bioluminescence_visible_in_metadata
        return [p for p in curated
                if bioluminescence_visible_in_metadata(p["visual_search_query"])]
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
    # Only subjects actually grounded in the topic may be used as a fallback
    # for further LLM suggestions; a rejected family must not re-enter here.
    allowed_objects = {x["object"].casefold() for x in curated}
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
        # Lexical stemming and stock-domain aliases bridge genuine synonyms
        # ('aurora borealis' vs 'northern lights', 'beaches' vs 'beach').
        # Reject unrelated LLM pivots but do not require identical words.
        if not related_to_topic(topic, obj, query, allowed_objects):
            continue
        seen.add(query.lower())
        curated.append(dict(main_character="", object=obj, action="ambient",
                            location="", time="", visual_search_query=query))
    return curated


def _lava_glow_score(path) -> float:
    """Cheap real-frame color cue for putting genuinely glowing lava first.

    Metadata and CLIP are still the eligibility gates; red/orange pixels
    only rank clips that have ALREADY passed those independent checks.
    Fail closed for scoring (keep existing order) if frame read fails.
    """
    import io
    import shutil
    import subprocess
    from PIL import Image

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg or not path:
        return 0.0
    values = []
    for time_seconds in (0.6, 2.4):
        try:
            proc = subprocess.run(
                [ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error",
                 "-ss", str(time_seconds), "-i", str(path),
                 "-vf", "scale=160:-2", "-frames:v", "1",
                 "-f", "image2pipe", "-vcodec", "mjpeg", "-"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                timeout=6, check=False)
            if proc.returncode or not proc.stdout:
                continue
            with Image.open(io.BytesIO(proc.stdout)) as frame:
                pixels = list(frame.convert("RGB").resize((128, 72)).getdata())
            hot = sum(1 for r, g, b in pixels
                      if r > 165 and g < 155 and b < 115
                      and r > 1.28 * g and r > 1.65 * b)
            values.append(hot / len(pixels))
        except (OSError, ValueError, subprocess.TimeoutExpired):
            continue
    return max(values, default=0.0)


def prioritize_lava_opening(topic, items, plans, scene_reports, *,
                            glow_score=None) -> bool:
    """Put the most visually striking verified lava shot at video start.

    Only changes order of already-verified, licensed, unique video clips.
    Every associated scene plan/report moves with its clip to preserve sync.
    Never change narration, invent footage, or reorder unrelated topics.
    """
    from topic_footage import is_lava_ocean_topic
    if not is_lava_ocean_topic(topic) or len(items) < 2:
        return False
    if not (len(items) == len(plans) == len(scene_reports)):
        raise ValueError("opening_footage_sync_error: mismatched verified video palette")
    scorer = glow_score or _lava_glow_score
    scores = [max(0.0, float(scorer(getattr(item, "path", None))))
              for item in items]
    index = max(range(len(scores)), key=lambda i: scores[i])
    if index == 0 or scores[index] < 0.008:
        return False
    for sequence in (items, plans, scene_reports):
        sequence.insert(0, sequence.pop(index))
    print(f"[OPENING FOOTAGE] promoted verified lava scene {index+1} "
          "to opening position", flush=True)
    return True


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
        error = ("media_preflight_no_topic_palette: no subject-grounded "
                 "stock queries could be derived from the topic")
        visuals.report.update(
            state="failed", strategy="v3_media_first", error=error,
            preflight_attempts=[])
        visuals._save()
        save_path = Path(os.getenv("MEDIA_FIRST_REPORT", "media-first-plan.json"))
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_text(json.dumps(
            {"strategy": "v3_media_first", "topic": topic,
             "state": "failed", "error": error, "selected": [], "attempts": []},
            ensure_ascii=False, indent=2), encoding="utf-8")
        raise RuntimeError(error)
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
    # Rank the ACTUAL first 1.2 seconds across all accepted real clips.
    # Fail before TTS if no vivid, moving, topic-relevant opening exists.
    from opening_impact import prioritize_opening
    opening_review = prioritize_opening(topic, items, plans, selected_rows)
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
    visuals.report["opening_review"] = opening_review
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
        "opening_review": opening_review,
        "selected": [
            {"index": i+1, "query": p["visual_search_query"],
             "object": p["object"], "source": m.source, "id": m.id,
             "sha256": m.extra.get("sha256"),
             "quality": m.extra.get("quality"),
             "license": m.extra.get("license"),
             "subject_screen": m.extra.get("match", {}).get("subject_screen"),
             "crop_focus_x": m.extra.get("match", {}).get("crop_focus_x")}
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
        "FIRST THREE SECONDS: the actual vertical opening shot must show the main "
        "filmable topic subject, not only the scenery around it. Start the "
        "spoken hook immediately, with an intriguing, true first 5-7 words. "
        "Never add a fabricated visual claim or an unsupported numerical shock hook.",
        "MEDIA-FIRST VERIFIED SHOTS. These clips are ALREADY obtained, measured, "
        "licensed and visually screened. The narration must be grounded in the "
        "topic; do not invent specific facts just to fit a picture.",
        f"Write EXACTLY {len(palette.plans)} scenes in this order. "
        "Each scene corresponds to the indicated real footage. "
        "Do NOT request new shots or more scenes. Write as few spoken words "
        "as needed to tell THIS true story naturally, without padding or forced "
        "30-second runtime. Every scene must fit its own verified unlooped clip.",
        "RETENTION PACING: The first scene must begin directly with the real, "
        "specific visual subject — never a greeting, channel intro, generic "
        "question repeated from the title or 'Did you know?'. Start with an "
        "accurate observation, then build curiosity naturally. The second "
        "scene must deliver a substantive new fact, not empty suspense. "
        "Each middle scene progresses the explanation with fresh information. "
        "The last scene clearly answers the topic and closes with a relevant "
        "fact, not 'like/comment/subscribe'. The facts must match the official "
        "sources or independently screened references; do not invent drama "
        "or state that illustrative footage is proof of an event.",
        "Every scene MUST remain scientifically truthful, without fake places, "
        "experiments, witnesses, exact measurements or dramatic invented facts. "
        "No precise quantities, numerical records or scientific measurements "
        "are supplied or verified for this topic. NEVER invent numerical "
        "measurements, rates, percentages, voltages or historical counts. "
        "Use reliable general scientific mechanisms instead. "
        "The image illustrates the subject; it is not a recording of the exact event.",
    ]
    from retention_storyboard import storyboard_writer_brief
    lines.append(storyboard_writer_brief(len(palette.plans), palette.planned_seconds))
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
