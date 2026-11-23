"""Recover a concise Short ONLY from independently source-approved scenes.

The fallback preserves narration exactly as it was approved by screen_narration,
without asking a free-tier model to improvise new scientific claims. It is a
last resort after repeated factuality rejections and not a substitute for
a full, independently rechecked storyboard, video/audio/license verification.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import re


def salvage_approved_narration(screenplay, science_report, *, min_scenes=2):
    """Return a shorter *candidate* or None; never assert it has passed QA.

    Only the internally produced, per-scene independently source-screened
    booleans/quotes are considered. Refuse incomplete, malformed, duplicate,
    missing or incorrectly indexed reports. Approved words and scene-specific
    visual contracts are byte-for-byte unchanged.
    """
    original = list(getattr(screenplay, "scenes", ()) or ())
    if not 2 <= len(original) <= 6:
        return None
    try:
        report = json.loads(Path(science_report).read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError):
        return None
    if (report.get("state") != "failed"
            or report.get("method") != "model_screened_reference"
            or report.get("error") != "source passage cannot substantiate all scene claims"):
        return None
    checks = report.get("scene_checks")
    if not isinstance(checks, list) or len(checks) != len(original):
        return None
    sources = report.get("sources")
    if not isinstance(sources, list):
        return None
    source_ids = {
        x.get("id") for x in sources
        if isinstance(x, dict) and isinstance(x.get("id"), str)}
    passed = []
    for index, row in enumerate(checks, 1):
        if (not isinstance(row, dict) or type(row.get("scene")) is not int
                or row["scene"] != index or type(row.get("supported")) is not bool):
            return None
        if not row["supported"]:
            continue
        narration = str(getattr(original[index-1], "narration", "") or "").strip()
        quote = str(row.get("quote") or "").strip()
        if (row.get("source_id") not in source_ids
                or len(quote) < 20
                or len(re.findall(r"\b[\w'-]+\b", narration)) < 5):
            return None
        passed.append(original[index - 1])
    if not min_scenes <= len(passed) < len(original):
        return None
    salvaged = deepcopy(screenplay)
    salvaged.scenes = deepcopy(passed)
    return salvaged
