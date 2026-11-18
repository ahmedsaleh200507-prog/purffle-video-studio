"""Conservative publication gate for unsupported exact science measurements.

This is NOT a fact-checker. Without independently retrieved references, a
generic educational Shorts script must not invent exact numeric measurements.
Reject-and-redraft BEFORE TTS is safer than voicing an unverified statistic.
"""
from __future__ import annotations

import re

# Detect numeric + quantitative claim, not bare dates in user-provided stories.
_MEASUREMENT = re.compile(
    r"(?<![\w])\d+(?:[.,]\d+)*\s*"
    r"(?:%|percent|percentage|°[cf]?|km/h|kph|mph|m/s|km|kilometers?|"
    r"met(?:er|re)s?|feet|miles?|watts?|kilowatts?|volts?|"
    r"millibars?|mbars?|mbar|pascals?|hectopascals?|hpa|"
    r"degrees?|celsius|fahrenheit|kelvin|tons?|tonnes?|"
    r"times|people|deaths?|years?|million|billion)(?=\s|[.,!?;:]|$)",
    re.IGNORECASE
)
# Generic causal scientific explainers don't require fabricated measurements.
_GENERAL_QUESTION = re.compile(
    r"^\s*(what|why|how|can|does|do|is|are|when)\b", re.IGNORECASE)


def validate_unsourced_quantities(script, topic: str) -> None:
    """Fail early if a general explainer invents specific quantitative claims.

    Validity of scientific sentences *without* numbers is NOT proven by this
    function; later editorial fact verification is still recommended.
    """
    if not _GENERAL_QUESTION.search(str(topic)):
        return
    for index, scene in enumerate(getattr(script, "scenes", []), 1):
        narration = str(getattr(scene, "narration", ""))
        found = _MEASUREMENT.search(narration)
        if found:
            raise RuntimeError(
                f"unverified_quantitative_claim: scene {index} uses "
                f"'{found.group(0)}' without an independently verified source")
