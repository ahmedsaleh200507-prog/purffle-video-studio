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


def ground_lightning_explainer(data: dict, topic: str, language: str,
                              scene_count: int | None = None) -> dict:
    """Replace hallucinated invented lightning cases in this generic explainer.

    This replaces narration, visuals AND description together so a fabricated
    claim cannot leak through captions or YouTube copy. All other topics,
    including user-supplied concrete historical lightning events, are untouched.
    """
    if not _lightning_repeated_topic(topic):
        return data
    source_scenes = _GERMAN_SCENES if language == "de" else _ENGLISH_SCENES
    if scene_count in (3, 4):
        # A footage-first production may have fewer verified clips than the
        # five beats of the original script. Use prewritten shorter, factual
        # beats instead of concatenating long narration beyond clip duration.
        if language == "de":
            short_scenes = [
                ("Ein Blitz kann dieselbe Stelle mehrfach treffen. Hohe, freistehende Objekte sind besonders gefährdet.",
                 "lightning", "lightning storm"),
                ("Ein nahender Blitzkanal kann sich mit einem Funken verbinden, der von einem hohen Objekt nach oben steigt.",
                 "cloud", "storm clouds"),
                ("Bei dieser Verbindung fließt sehr starker Strom. Bei Donner geh ins Haus, niemals unter einen einzelnen Baum.",
                 "tree", "trees blowing in wind"),
            ]
        else:
            short_scenes = [
                ("Lightning can hit the same place repeatedly. Tall, isolated objects are struck more often.",
                 "lightning", "lightning storm"),
                ("A descending lightning channel can connect with an upward spark from a tall object.",
                 "cloud", "storm clouds"),
                ("That connection carries a powerful current. When you hear thunder, go indoors, never beneath an isolated tree.",
                 "tree", "trees blowing in wind"),
            ]
        if scene_count == 4:
            short_scenes = [source_scenes[0], source_scenes[1],
                            source_scenes[2], source_scenes[-1]]
        source_scenes = short_scenes
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
        "category": "science",
        "hashtags": ["#Shorts", "#Lightning", "#Science"],
        "tags": ["lightning", "thunderstorm", "repeated lightning strikes",
                 "lightning science", "lightning safety"],
        "review": [],
        "scenes": scenes,
    }


# Editor-reviewed factual summaries based on official USGS/NPS and NOAA guidance.
# These are narrow facts dossiers for exact science-explainer subjects, not
# evidence that arbitrary new Groq topics are independently fact-checked.
# https://www.nps.gov/subjects/geology/plate-tectonics-oceanic-hotspots.htm
# https://www.usgs.gov/observatories/hvo/evolution-hawaiian-volcanoes
# https://www.noaa.gov/jetstream/tropical/tropical-cyclone-introduction/tropical-cyclone-structure
# https://www.aoml.noaa.gov/hrd/tcfaq/A11.html?print=yes
_DOCUMENTARY_FACTS = {
    "volcanic_island": {
        "en": [
            "Some volcanic islands begin as eruptions on the ocean floor.",
            "Repeated eruptions build layers of lava and rock, gradually creating an underwater mountain.",
            "When that mountain rises above sea level, new land appears as a volcanic island.",
            "The island remains connected to the ocean floor, while waves reshape its coastline.",
        ],
        "de": [
            "Manche Vulkaninseln entstehen durch Ausbrüche auf dem Meeresboden.",
            "Wiederholte Ausbrüche schichten Lava und Gestein auf und bilden einen Unterwasserberg.",
            "Wächst dieser Berg über den Meeresspiegel, entsteht eine neue Vulkaninsel.",
            "Die Insel bleibt mit dem Meeresboden verbunden. Wellen verändern später ihre Küste.",
        ],
        "title": {"en": "How Volcanoes Create New Islands",
                  "de": "Wie Vulkane neue Inseln erschaffen"},
        "description": {"en": "Lava and erupted rock build underwater volcanic mountains. When they rise above sea level, new islands emerge.",
                        "de": "Lava und Gestein bauen Unterwasservulkane auf. Über dem Meeresspiegel entstehen daraus neue Inseln."},
        "tags": ["volcanic islands", "underwater volcanoes", "lava", "geology"],
    },
    "hurricane_eye": {
        "en": [
            "A hurricane can have a relatively calm eye, surrounded by its dangerous eyewall.",
            "Moist air rises through the eyewall, feeding towering storm clouds and heavy rain.",
            "Air in the eye slowly sinks and warms, often allowing clouds to thin.",
            "But the calm is temporary. Dangerous eyewall winds can return when the eye passes.",
        ],
        "de": [
            "Das Auge eines Hurrikans ist oft vergleichsweise ruhig, umgeben von gefährlichen Winden.",
            "An der Augenwand steigt feuchte Luft auf und bildet mächtige Gewitterwolken.",
            "Im Auge sinkt Luft ab und erwärmt sich. Wolken können sich auflösen.",
            "Doch die Ruhe ist vorübergehend. Danach können die heftigen Winde zurückkehren.",
        ],
        "title": {"en": "Why Is the Eye of a Hurricane Calm?",
                  "de": "Warum ist das Auge eines Hurrikans ruhig?"},
        "description": {"en": "An explanation of hurricane eyes, rising eyewall air and sinking air near the storm center, based on NOAA storm science.",
                        "de": "Das Auge eines Hurrikans erklärt: Aufsteigen in der Augenwand und absinkende Luft im Zentrum."},
        "tags": ["hurricane eye", "eyewall", "tropical cyclones", "weather"],
    },
}


def verified_documentary_kind(topic: str) -> str | None:
    """Recognize exact broad explainers; other topics preserve Groq output."""
    raw = str(topic or "").casefold()
    import re
    text = re.sub(r"[^a-z ]", " ", raw)
    tokens = set(text.split())
    if (tokens & {"volcano", "volcanoes", "volcanic"}) and (
            tokens & {"island", "islands"}) and (
            tokens & {"create", "created", "form", "formed", "make", "build"}):
        return "volcanic_island"
    if (tokens & {"hurricane", "hurricanes", "cyclone", "cyclones"}) and (
            tokens & {"eye", "inside", "center", "centre"}):
        return "hurricane_eye"
    return None


def ground_verified_documentary(data: dict, topic: str, language: str,
                                scene_count: int | None = None) -> dict:
    """Use source-reviewed narration for the known #71 science topics.

    Footage visual queries are authoritative only in align_script_to_palette;
    factual template text here is not changed to 'explain' unrelated footage.
    """
    kind = verified_documentary_kind(topic)
    if not kind:
        return data
    info = _DOCUMENTARY_FACTS[kind]
    language = "de" if str(language).startswith("de") else "en"
    narration = list(info[language])
    if scene_count == 3:
        # Four verified scientific points can be compressed without changing
        # any causal mechanisms or introducing new measurements.
        if kind == "volcanic_island":
            narration = [
                narration[0],
                narration[1],
                "When the mountain rises above sea level, an island emerges, firmly connected to the seafloor."
                if language == "en" else
                "Wächst der Berg über den Meeresspiegel, entsteht eine Insel, fest verbunden mit dem Meeresboden.",
            ]
        else:
            narration = [
                narration[0],
                narration[1] if language == "en" else narration[1],
                "Air sinks and warms in the eye. But dangerous eyewall winds can return after the calm."
                if language == "en" else
                "Im Auge sinkt Luft ab. Doch nach der Ruhe können gefährliche Winde zurückkehren.",
            ]
    scenes = [{
        "narration": sentence, "speaker": "A", "search_query": "",
        "image_prompt": "", "main_character": "", "object": "volcano" if kind == "volcanic_island" else "hurricane",
        "action": "ambient", "location": "", "time": "",
        "visual_search_query": "volcano erupting" if kind == "volcanic_island" else "hurricane satellite clouds",
        "emphasis": [], "emoji": "",
    } for sentence in narration]
    return {
        **data,
        "title": info["title"][language],
        "hook_text": info["title"][language],
        "description": info["description"][language],
        "scenes": scenes,
        "category": "education",
        "hashtags": ["#Shorts", "#Science", "#Nature"],
        "tags": list(info["tags"]),
        "review": [],
    }
