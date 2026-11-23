"""First-seconds opening quality gate for real-camera Purffle Shorts.

Every selected clip already passed the independent license, resolution, motion,
metadata and sampled CLIP checks. This module ONLY ranks those accepted clips
using first-second frames. It never creates visuals, edits script facts, or
claims measurable human retention from pixels.
"""
from __future__ import annotations

import io
import math
import statistics
from pathlib import Path
import shutil
import subprocess


def _first_frames(path: Path, *, focus: float = 0.5, seconds=(0.15, 1.15)):
    """Sample exactly the opening seconds of the source used by the renderer."""
    from PIL import Image
    binary = shutil.which("ffmpeg")
    if not binary or not path or not Path(path).is_file():
        return []
    result = []
    for second in seconds:
        try:
            process = subprocess.run(
                [binary, "-hide_banner", "-nostdin", "-loglevel", "error",
                 "-threads", "2", "-ss", str(second), "-i", str(path),
                 "-vf", ("scale=192:340:force_original_aspect_ratio=increase,"
                          "crop=192:340:x='max(0,min(iw-ow,iw*"
                          f"{focus:.5f}" + "-ow/2))':y='(ih-oh)/2',setsar=1"),
                 "-frames:v", "1", "-f", "image2pipe",
                 "-vcodec", "mjpeg", "-"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                timeout=8, check=False)
            if process.returncode or not process.stdout:
                return []
            with Image.open(io.BytesIO(process.stdout)) as frame:
                result.append(frame.convert("RGB").copy())
        except (OSError, ValueError, subprocess.TimeoutExpired):
            return []
    return result


def _evaluate_frames(frames) -> dict:
    """Small, transparent scoring heuristic; not an AI promise of virality."""
    from PIL import ImageChops, ImageFilter, ImageStat
    if len(frames) != 2:
        return {"verified": False, "reason": "opening_frame_decode_failed"}
    a, b = frames
    if a.size != b.size:
        return {"verified": False, "reason": "opening_frame_shape_mismatch"}
    a_luma, b_luma = a.convert("L"), b.convert("L")
    first = ImageStat.Stat(a_luma)
    second = ImageStat.Stat(b_luma)
    brightness = float(first.mean[0])
    contrast = float(first.stddev[0])
    detail = float(ImageStat.Stat(
        a_luma.filter(ImageFilter.FIND_EDGES).crop((3, 3, a.width-3, a.height-3))
    ).mean[0])
    motion = float(ImageStat.Stat(ImageChops.difference(a_luma, b_luma)).mean[0])
    rgb = ImageStat.Stat(a)
    color_spread = max(rgb.mean) - min(rgb.mean)
    # Hot red/orange pixels in the FIRST second, not a later reveal.
    pixels = list(a.resize((64, 112)).getdata())
    hot = sum(1 for r,g,blue in pixels
              if r > 180 and g < 145 and blue < 105
              and r > 1.42 * (g+1) and r > 1.65 * (blue+1)) / len(pixels)
    bright = 13 <= brightness <= 242 and second.mean[0] >= 10
    visible = (bright and contrast >= 9 and detail >= 2.2
               and motion >= .85)
    # Normalize measured motion/texture/contrast, not subjective "viral" scores.
    impact = round(100 * (
        .36 * min(motion/24, 1) +
        .28 * min(contrast/51, 1) +
        .24 * min(detail/25, 1) +
        .12 * min(color_spread/45, 1)
    ), 1) if visible else 0.0
    return {
        "verified": bool(visible),
        "reason": "first_seconds_visible_and_moving" if visible else
                  "weak_dark_blurry_or_static_intro",
        "impact": impact,
        "brightness": round(brightness, 2),
        "contrast": round(contrast, 2),
        "motion": round(motion, 2),
        "detail": round(detail, 2),
        "hot_lava_ratio": round(hot, 4),
    }


def inspect_opening(path: Path) -> dict:
    """Inspect decoded real pixels, never trust only provider metadata."""
    return _evaluate_frames([frame.resize((96, 170))
                             for frame in _first_frames(path)])


def _semantic_subject_screen(
        frames, specification, *, scorer=None, require_all_frames=False,
        minimum_margin=.012):
    """Contrast actual 9:16 scene frames with subject vs scenery.

    This is CLIP-based comparative screening, NOT an object detector or a
    measured likelihood of viewer retention.
    """
    if len(frames) < 2:
        return {"verified": False, "reason": "subject_frames_unavailable"}
    if scorer is None:
        from media_validation import SceneMatcher
        scorer = SceneMatcher()._similarities
    captions = [specification["positive"], *specification["negatives"]]
    matrix = scorer(frames, captions)
    if len(matrix) != len(frames) or any(len(row) != len(captions) for row in matrix):
        raise RuntimeError("opening_subject_unverified: local visual scorer malformed")
    score = statistics.median(float(row[0]) for row in matrix)
    margin = statistics.median(
        float(row[0]) - max(float(x) for x in row[1:]) for row in matrix)
    # #93: median similarity barely favored "lightning" over ordinary
    # storm clouds (0.0135), or "iceberg" over a dark sea (0.020).
    # Critical topics can demand a stronger independent visual margin.
    # Persistent physical objects must remain in every sampled scene frame,
    # including close to the final edited frame, not only the opening.
    margins = [float(row[0]) - max(float(x) for x in row[1:])
               for row in matrix]
    all_visible = all(float(row[0]) >= .235 and delta >= .012
                      for row, delta in zip(matrix, margins))
    accepted = (score >= .235 and margin >= minimum_margin
                and (not require_all_frames or all_visible))
    return {
        "verified": bool(accepted),
        "sampled_subject_frames": len(frames),
        "all_sampled_frames_subject_visible": bool(all_visible),
        "required_subject_margin": round(float(minimum_margin), 4),
        "subject": specification["subject"],
        "subject_similarity": round(score, 4),
        "subject_minus_scenery": round(margin, 4),
        "reason": ("subject_favored_over_scenery" if accepted else
                   "opening_subject_not_prominent_enough"),
        "method": "local_clip_contrast_actual_9_16_opening_crop",
        "limitations": "Similarity cannot prove exact objects or retention",
    }


def _measure_opening(path, focus, specification, *, preverified_subject=None):
    frames = _first_frames(path, focus=focus)
    result = _evaluate_frames([f.resize((96, 170)) for f in frames])
    if specification is not None and result.get("verified"):
        # The candidate-level gate already ran on these same original opening
        # seconds and crop focus. Reuse its trusted source result to avoid
        # an unnecessary second CLIP inference for every accepted shot.
        result["subject_screen"] = (
            dict(preverified_subject) if preverified_subject is not None else
            _semantic_subject_screen(frames, specification))
    return result


def prioritize_opening(topic, items, plans, reports, *, analyzer=None,
                       semantic_analyzer=None) -> dict:
    """Put strongest verified FIRST-SECOND shot first for all Shorts.

    Reorder clip+visual-plan+source-provenance together *before* screenplay
    generation. Do not publish if no valid opening can be inspected. Test
    doubles without media bytes may skip inspection; real media paths never do.
    """
    from topic_footage import is_lava_ocean_topic, opening_subject_prompts
    specification = opening_subject_prompts(topic)
    if not len(items) == len(plans) == len(reports):
        raise RuntimeError("opening_quality_unverified: scene/plan/report lengths differ")
    if not items:
        raise RuntimeError("opening_quality_unverified: no footage")
    paths = [getattr(item, "path", None) for item in items]
    if not any(paths):
        # Lightweight offline contract doubles have no real video files.
        return {"state": "not_evaluated_without_real_video", "scene_count": len(items)}
    if not all(paths):
        raise RuntimeError("opening_quality_unverified: one source has no video file")
    analyze = analyzer or inspect_opening
    lava = is_lava_ocean_topic(topic)
    from topic_footage import words
    topic_tokens = words(topic)
    steel_ship = bool(({"steel", "ship", "float"} <= topic_tokens
                       or {"steel", "ships", "float"} <= topic_tokens)
                      and not {"submarine", "sinking", "capsize"} & topic_tokens)
    choices = []
    for idx, (item, plan, report, path) in enumerate(zip(items, plans, reports, paths)):
        focus = float(getattr(item, "extra", {}).get("match", {}).get(
            "crop_focus_x", report.get("match", {}).get("crop_focus_x", .5)))
        if not math.isfinite(focus) or not 0 <= focus <= 1:
            raise RuntimeError("opening_quality_unverified: invalid scene crop focus")
        measurements = dict(analyze(path) if analyzer is not None else
                            _measure_opening(
                                path, focus, specification,
                                preverified_subject=report.get("match", {}).get("subject_screen")))
        # Offline doubles with an injected pixel analyzer avoid a live CLIP
        # dependency; a separate injected semantic analyzer tests this branch.
        if semantic_analyzer is not None and specification is not None:
            measurements["subject_screen"] = dict(
                semantic_analyzer(path, specification, focus))
        subject_screen = measurements.get("subject_screen")
        if subject_screen is not None and subject_screen.get("verified") is not True:
            measurements["verified"] = False
            measurements["reason"] = "opening_subject_not_prominent_enough"
        source_hint = str(
            report.get("license", {}).get("source_page") or
            report.get("source_page") or report.get("source_url") or "").casefold()
        if (steel_ship and any(term in source_hint for term in (
                "abandoned", "shipwreck", "wrecked", "beached",
                "dry-dock", "drydock"))):
            # #83's highest-impact Coverr shot was tagged "abandoned
            # ship in Tierra del Fuego". An attractive wreck is not
            # evidence that a steel ship FLOATS. Prefer verified in-water
            # vessel footage; do not promote ambiguous wrecks as the hook.
            measurements["verified"] = False
            measurements["reason"] = "opening_source_does_not_demonstrate_floating_ship"
        if measurements.get("verified") is not True:
            rating = -1.0
        else:
            impact = max(0.0, min(100, float(measurements["impact"])))
            visual = report.get("match", {}).get("visual_score") or 0.0
            try:
                relevance = max(0.0, min(1.0, float(visual)))
            except (TypeError, ValueError):
                relevance = 0.0
            # Only trust an *early* lava glimpse as a gripping lava opening.
            hot = float(measurements.get("hot_lava_ratio") or 0)
            subject_margin = (float(subject_screen["subject_minus_scenery"])
                              if subject_screen else 0.0)
            rating = (impact + 18.0 * relevance +
                      min(14.0, max(0.0, subject_margin) * 160) +
                      (min(40.0, 400 * hot) if lava else 0.0))
        measurements.update(original_scene=idx + 1, rank=round(rating, 2),
                            query=str(plan.get("visual_search_query", ""))[:100])
        choices.append(measurements)
    contenders = [
        (i, row["rank"]) for i, row in enumerate(choices)
        if row.get("verified") is True and row["rank"] >= 24.0
        and (not lava or row.get("hot_lava_ratio", 0) >= .006)
    ]
    if not contenders:
        raise RuntimeError(
            "opening_quality_unverified: no strong relevant moving footage in "
            "the first 1.2 seconds; reject before voice/render")
    winner, _ = max(contenders, key=lambda pair: pair[1])
    if winner:
        for group in (items, plans, reports):
            group.insert(0, group.pop(winner))
    result = {"state": "selected", "original_scene": winner + 1,
              "first_seconds_inspected": True, "crop_focus_aware": True,
              "no_opening_title": True, "clip_scores": choices,
              "chosen_score": choices[winner]["rank"],
              "subject_screen": choices[winner].get("subject_screen"),
              "visual_confidence": ("strong" if choices[winner]["rank"] >= 68
                                    else "medium"),
              "visual_confidence_type": "editorial_heuristic_not_retention_prediction"}
    print(f"[OPENING QUALITY] selected original scene {winner+1} / "
          f"{len(items)} first-second score {choices[winner]['rank']:.1f}",
          flush=True)
    return result
