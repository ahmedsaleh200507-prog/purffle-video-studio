"""First-seconds opening quality gate for real-camera Purffle Shorts.

Every selected clip already passed the independent license, resolution, motion,
metadata and sampled CLIP checks. This module ONLY ranks those accepted clips
using first-second frames. It never creates visuals, edits script facts, or
claims measurable human retention from pixels.
"""
from __future__ import annotations

import io
import math
from pathlib import Path
import shutil
import subprocess


def _first_frames(path: Path):
    """Sample exactly the opening seconds of the source used by the renderer."""
    from PIL import Image
    binary = shutil.which("ffmpeg")
    if not binary or not path or not Path(path).is_file():
        return []
    result = []
    for second in (0.15, 1.15):
        try:
            process = subprocess.run(
                [binary, "-hide_banner", "-nostdin", "-loglevel", "error",
                 "-threads", "2", "-ss", str(second), "-i", str(path),
                 "-vf", "scale=96:170:force_original_aspect_ratio=increase,"
                        "crop=96:170,setsar=1",
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
    return _evaluate_frames(_first_frames(path))


def prioritize_opening(topic, items, plans, reports, *, analyzer=None) -> dict:
    """Put strongest verified FIRST-SECOND shot first for all Shorts.

    Reorder clip+visual-plan+source-provenance together *before* screenplay
    generation. Do not publish if no valid opening can be inspected. Test
    doubles without media bytes may skip inspection; real media paths never do.
    """
    from topic_footage import is_lava_ocean_topic
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
    choices = []
    for idx, (item, plan, report, path) in enumerate(zip(items, plans, reports, paths)):
        measurements = dict(analyze(path))
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
            rating = impact + 18.0 * relevance + (min(40.0, 400 * hot) if lava else 0.0)
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
              "first_seconds_inspected": True,
              "no_opening_title": True, "clip_scores": choices,
              "chosen_score": choices[winner]["rank"]}
    print(f"[OPENING QUALITY] selected original scene {winner+1} / "
          f"{len(items)} first-second score {choices[winner]['rank']:.1f}",
          flush=True)
    return result
