"""Ground a small, explicitly supported set of educational stories in facts.

Other topics are left to the language model (with stronger factual prompts).
No external request or paid API is required. These fact-driven narrations are
NOT footage of any particular named event or research experiment.

Sources (checked 2026-11-18):
https://www.nssl.noaa.gov/education/svrwx101/lightning/faq/
https://www.nssl.noaa.gov/education/svrwx101/lightning/
https://www.weather.gov/safety/lightning-myths
https://www.weather.gov/safety/lightning-tips
"""
from __future__ import annotations

import re


def _lightning_repeated_topic(topic: str) -> bool:
    norm = re.sub(r"[^a-z ]", " ", str(topic).casefold())
    return (
        ("lightning" in norm or "thunderbolt" in norm)
        and (
            "same place" in norm
            or "same spot" in norm
            or "same location" in norm
            or "same object" in norm
            or "again and again" in norm
            or "strike twice" in norm
            or "strikes twice" in norm
            or "repeated" in norm
        )
    )


_ENGLISH_SCENES = [
    ("Lightning can strike the same spot again and again. So why does that happen?",
     "lightning", "lightning storm"),
    ("Tall, isolated objects such as trees and towers are more likely to be struck.",
     "tree", "trees blowing in wind"),
    ("As a lightning channel approaches, a tall object may send an upward spark that connects with it.",
     "cloud", "storm clouds"),
    ("That connection allows an enormous electrical current to rush through the lightning channel.",
     "lightning", "lightning flashes night sky"),
    ("Never shelter under an isolated tree during a storm. When you hear thunder, go indoors.",
     "cloud", "storm clouds moving"),
]

_GERMAN_SCENES = [
    ("Ein Blitz kann dieselbe Stelle immer wieder treffen. Aber warum passiert das?",
     "lightning", "lightning storm"),
    ("Hohe, freistehende Objekte wie Bäume und Türme werden besonders häufig getroffen.",
     "tree", "trees blowing in wind"),
    ("Nähert sich ein Blitzkanal, können hohe Objekte einen Funken nach oben aussenden.",
     "cloud", "storm clouds"),
    ("Wenn sich beide verbinden, fließt ein enorm starker elektrischer Strom.",
     "lightning", "lightning flashes night sky"),
    ("Suche niemals Schutz unter einem einzelnen Baum. Wenn du Donner hörst, geh ins Haus.",
     "cloud", "storm clouds moving"),
]


def ground_lightning_explainer(data: dict, topic: str, language: str) -> dict:
    """Replace hallucinated invented lightning cases in this generic explainer.

    This replaces narration, visuals AND description together so a fabricated
    claim cannot leak through captions or YouTube copy. All other topics,
    including user-supplied concrete historical lightning events, are untouched.
    """
    if not _lightning_repeated_topic(topic):
        return data
    source_scenes = _GERMAN_SCENES if language == "de" else _ENGLISH_SCENES
    scenes = []
    for narration, subject, query in source_scenes:
        plan = {
            "main_character": "", "object": subject, "action": "ambient",
            "location": "", "time": "", "visual_search_query": query,
        }
        scenes.append({
            "narration": narration, "search_query": query,
            "image_prompt": "", "speaker": "A",
            **plan,
        })
    if language == "de":
        title = "Warum schlägt ein Blitz zweimal an derselben Stelle ein?"
        description = (
            "Warum Blitze dieselbe Stelle öfter treffen: "
            "Erklärungen zu hohen Objekten, Aufwärtsentladungen und Gewitterschutz."
        )
    else:
        title = "Why Lightning Strikes the Same Place Again ⚡"
        description = (
            "Why lightning can strike the same place repeatedly: "
            "tall objects, connecting upward sparks, and storm safety."
        )
    return {
        **data,
        "title": title,
        "hook_text": scenes[0]["narration"],
        "description": description,
        "scenes": scenes,
    }
