"""Repair an unfilmable visual plan without rewriting verified science.

Free stock catalogs cannot show individual air molecules scattering photons.
Film an OBSERVABLE result/context instead, and clearly mark that the stock
image is illustrative. Never change the science-screened narration or claim
that B-roll proves an invisible physical mechanism.

This module is deliberately narrow until real-video false positives are
measured. It is not a general waiver of visual/action/licensing checks.
"""
from __future__ import annotations

import copy
import json
import re


_SKY_TOPIC = re.compile(
    r"\bsky\b.{0,50}\bblue\b|\bblue\b.{0,50}\bsky\b"
    r"|\bhimmel\b.{0,50}\bblau\w*|\bblau\w*.{0,50}\bhimmel\b",
    re.I,
)
_INVISIBLE = re.compile(
    r"\b(?:molecul\w*|atom\w*|photon\w*|scatter\w*|"
    r"particle\w*|rayleigh|wave\s*length\w*|wavelength\w*|"
    r"lichtstreu\w*|streuung|molekül\w*|teilchen)\b",
    re.I,
)
# Each query describes observable real outdoor footage, not light scattering
# inside a molecule. Stock sites contain sky/daylight videos for these shots.
# Different slots seek complementary scenes instead of looping one shot.
_FILMABLE_SKY = (
    ("sky", "ambient", "blue sky white clouds"),
    ("sky", "ambient", "sunlight blue sky clouds"),
    ("sky", "ambient", "blue sky moving clouds timelapse"),
    ("sky", "ambient", "clear daytime sky horizon"),
)


def visible_context_repair(screenplay, topic, unavailable_scenes):
    """Return a science-identical storyboard with filmable visual intents.

    Return None if no demonstrably unfilmable science-specific scene in this
    narrow, well-understood sky/atmosphere family can be repaired. All original
    scene fields including narration, speaker, titles and timing are kept.
    The full stock clip eligibility checks are run again after this change.
    """
    if not _SKY_TOPIC.search(str(topic or "")):
        return None
    original = list(getattr(screenplay, "scenes", ()) or ())
    if not 2 <= len(original) <= 6:
        return None
    slots = set()
    for row in unavailable_scenes or ():
        index = row.get("scene") if isinstance(row, dict) else row
        if type(index) is int and 1 <= index <= len(original):
            slots.add(index)
    if not slots:
        return None
    revised = copy.deepcopy(screenplay)
    changed = False
    for index in sorted(slots):
        scene = revised.scenes[index-1]
        query = str(getattr(scene, "visual_search_query", "") or "")
        subject = str(getattr(scene, "object", "") or "")
        narration = str(getattr(scene, "narration", "") or "")
        # Only swap explicit molecular/scattering visual searches. Don't
        # replace an already-directly-filmable sky clip with generic filler
        # simply because that candidate failed a license or crop gate.
        if not _INVISIBLE.search(" ".join((query, subject))):
            continue
        if not _INVISIBLE.search(narration):
            continue
        obj, action, stock_query = _FILMABLE_SKY[(index-1) % len(_FILMABLE_SKY)]
        scene.main_character = ""
        scene.object = obj
        scene.action = action
        scene.location = "outdoors"
        scene.time = "day"
        scene.visual_search_query = stock_query
        scene.search_query = stock_query
        plan = {
            "main_character": "", "object": obj, "action": action,
            "location": "outdoors", "time": "day",
            "visual_search_query": stock_query,
        }
        scene.image_prompt = json.dumps(plan, ensure_ascii=False)
        # Explicitly labelled in reports as illustrative_subject when
        # passed through visual_director.build_contract. Do not change speech!
        changed = True
    return revised if changed else None
