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
    "lightning_thunder_delay": {
        "en": [
            "Lightning flashes and thunder happen together during a storm.",
            "But light moves through air much faster than sound.",
            "That is why you see the bright flash before the rumble reaches your ears.",
            "A longer pause usually means the lightning is farther away. Stay safe indoors during storms.",
        ],
        "de": [
            "Blitz und Donner entstehen bei einem Gewitter praktisch gleichzeitig.",
            "Licht bewegt sich viel schneller durch die Luft als Schall.",
            "Deshalb siehst du den Blitz, bevor du den Donner hörst.",
            "Je länger die Pause, desto weiter ist der Blitz meist entfernt. Bei Gewitter bleib im Haus.",
        ],
        "title": {
            "en": "Why Do We See Lightning Before Hearing Thunder?",
            "de": "Warum sehen wir Blitze vor dem Donner?",
        },
        "description": {
            "en": "Thunder and lightning happen together. Light travels much faster than sound, so we see the flash before hearing the rumble.",
            "de": "Licht ist viel schneller als Schall. Deshalb sieht man den Blitz, bevor man den Donner hört.",
        },
        "tags": ["lightning", "thunder", "sound", "storms", "science"],
    },
    "northern_lights_glow": {
        "en": [
            "Northern lights are colorful displays high in Earth's atmosphere.",
            "Energetic electrons follow Earth's magnetic field toward polar regions.",
            "They collide with oxygen and nitrogen, causing these gases to release light.",
            "That glowing light forms colorful curtains across polar night skies.",
        ],
        "de": [
            "Polarlichter leuchten hoch in der Atmosphäre der Erde.",
            "Energiereiche Elektronen folgen dem Erdmagnetfeld zu den Polargebieten.",
            "Sie stoßen mit Sauerstoff und Stickstoff zusammen. Dabei entsteht Licht.",
            "Dieses Licht zeigt sich als farbige Schleier am Nachthimmel.",
        ],
        "title": {
            "en": "Why Do the Northern Lights Glow?",
            "de": "Warum leuchten die Nordlichter?",
        },
        "description": {
            "en": "Auroras are created when energetic electrons excite gases in Earth's upper atmosphere, releasing colorful light.",
            "de": "Energiereiche Elektronen regen Gase in der oberen Atmosphäre an. Dabei entsteht das farbige Polarlicht.",
        },
        "tags": ["northern lights", "aurora borealis", "oxygen", "nitrogen", "space weather"],
    },
    "ocean_waves": {
        # Source-constrained educational explanation, not LLM fact guessing.
        # NOAA Ocean Exploration: https://oceanexplorer.noaa.gov/ocean-fact/waves/
        # NOAA National Ocean Service: https://oceanservice.noaa.gov/education/tutorial_currents/03coastal1.html
        # NOAA NDBC: https://www.ndbc.noaa.gov/education/pacwave.shtml
        "en": [
            "Most ocean surface waves begin when wind blows across the water.",
            "The moving wind transfers energy to the surface, turning small ripples into growing waves.",
            "Their size depends on wind speed, how long it blows, and the distance it travels over water.",
            "As waves reach shallow water, they become steeper and can break along the shore.",
        ],
        "de": [
            "Die meisten Meereswellen entstehen, wenn Wind über die Wasseroberfläche weht.",
            "Der Wind überträgt Energie auf das Wasser. Aus kleinen Wellen werden größere Wellen.",
            "Ihre Größe hängt von Windstärke, Dauer und der Strecke über dem Wasser ab.",
            "In flachem Wasser werden Wellen steiler und können an der Küste brechen.",
        ],
        "title": {
            "en": "Why Do Ocean Waves Form?",
            "de": "Warum entstehen Meereswellen?",
        },
        "description": {
            "en": "Wind transfers energy to ocean water. Wind speed, duration and distance affect wave size, while shallow water causes breaking waves.",
            "de": "Wind überträgt Energie auf das Meer. Stärke, Dauer und Strecke beeinflussen die Wellenhöhe; in flachem Wasser brechen Wellen.",
        },
        "tags": ["ocean waves", "wind", "surf", "wave formation", "ocean science"],
    },
    "lava_ocean_entry": {
        # US Geological Survey, Hawaiian Volcano Observatory:
        # https://www.usgs.gov/observatories/hvo/science/lava-entering-ocean
        # https://www.usgs.gov/news/volcano-watch-what-happens-when-lava-flows-sea
        "en": [
            "Glowing lava pours into the ocean, and huge clouds of steam rise above the coast.",
            "The hot lava boils seawater while cooling and breaking into fragments of rock.",
            "The steam plume can carry acidic gases and tiny particles of volcanic glass.",
            "And unstable new lava deltas can collapse, sometimes triggering dangerous steam explosions along the coast.",
        ],
        "de": [
            "Glühende Lava fließt ins Meer. Über der Küste steigen große Dampfwolken auf.",
            "Die heiße Lava erhitzt Meerwasser und zerbricht beim Abkühlen in Gesteinsstücke.",
            "Die Dampfwolken können saure Gase und winzige Partikel aus vulkanischem Glas enthalten.",
            "Neu entstandene Lavaküsten können einstürzen und dabei gefährliche Dampfexplosionen auslösen.",
        ],
        "title": {
            "en": "What Happens When Lava Hits the Ocean?",
            "de": "Was passiert, wenn Lava ins Meer fließt?",
        },
        "description": {
            "en": "USGS explains how lava entering the ocean creates steam, rock fragments and hazardous plumes; unstable lava deltas may collapse.",
            "de": "Lava im Meer erzeugt Dampf, Gesteinssplitter und gefährliche Schwaden; instabile Lavaküsten können einstürzen.",
        },
        "tags": ["lava", "ocean", "volcano", "steam", "geology", "USGS"],
    },
    "ocean_glow_bioluminescence": {
        # NOAA Ocean Exploration and Smithsonian Ocean educational sources:
        # https://oceanexplorer.noaa.gov/ocean-fact/bioluminescence/
        # https://ocean.si.edu/ocean-life/six-ways-see-ocean-ocean-bioluminescence
        "en": [
            "Some ocean waves can glow bright blue at night.",
            "The light comes from tiny marine organisms, including certain plankton, not from the water itself.",
            "Movement in the water can trigger those organisms to flash.",
            "This natural light is called bioluminescence. It is produced by a chemical reaction inside living organisms.",
        ],
        "de": [
            "Manche Meereswellen können nachts blau leuchten.",
            "Das Licht stammt von winzigen Meeresorganismen, darunter bestimmtem Plankton, und nicht vom Wasser selbst.",
            "Durch Bewegung im Wasser können diese Organismen aufleuchten.",
            "Das Licht heißt Biolumineszenz und entsteht durch eine chemische Reaktion in Lebewesen.",
        ],
        "title": {"en": "Why Does the Ocean Glow Blue at Night?",
                  "de": "Warum leuchtet das Meer nachts blau?"},
        "description": {
            "en": "Some plankton emit blue light when the water moves. The phenomenon is called bioluminescence.",
            "de": "Manches Plankton erzeugt bei Bewegung blaues Licht: Biolumineszenz.",
        },
        "tags": ["bioluminescence", "glowing ocean", "glowing plankton", "marine science"],
    },
    "mirror_condensation": {
        "en": [
            "Hot shower water evaporates and makes bathroom air humid.",
            "The mirror often stays cooler than the surrounding moist air.",
            "Water vapor condenses into tiny liquid droplets on the mirror.",
            "Those droplets make the mirror look foggy. This is condensation.",
        ],
        "de": [
            "Beim Duschen verdunstet warmes Wasser. Die Badezimmerluft wird feucht.",
            "Der Spiegel bleibt oft kühler als die feuchte Luft.",
            "Dort kondensiert Wasserdampf und bildet winzige Tropfen auf dem Glas.",
            "Die Tropfen lassen den Spiegel beschlagen. Das nennt man Kondensation.",
        ],
        "title": {"en": "Why Does Your Bathroom Mirror Fog Up?",
                  "de": "Warum beschlägt der Badezimmerspiegel?"},
        "description": {
            "en": "A warm shower increases bathroom humidity. Water vapor condenses into tiny droplets on the cooler mirror.",
            "de": "Beim warmen Duschen wird die Luft feucht. Am kühleren Spiegel kondensiert Wasserdampf zu kleinen Wassertropfen.",
        },
        "tags": ["bathroom mirror", "condensation", "humidity", "water vapor"],
    },
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
    # Recognize only the ordinary bathroom-mirror explanation, not unrelated
    # uses of a mirror or unrelated fog/weather topics.
    if ("lightning" in tokens and "thunder" in tokens
            and ({"before", "hearing", "hear", "see", "first"} & tokens)):
        return "lightning_thunder_delay"
    if (("northern" in tokens and ("lights" in tokens or "light" in tokens)
         and ({"glow", "shine", "colors", "colour", "why"} & tokens))
        or ("aurora" in tokens and ({"glow", "shine", "colors", "colour"} & tokens))):
        return "northern_lights_glow"
    # Match the ordinary wind-driven wave explainer only. Do not replace
    # tsunami, tides, swell-specific, rogue-wave or earthquake explanations.
    if (tokens & {"wave", "waves", "wellen", "meereswellen"}
        and tokens & {"ocean", "sea", "meereswellen", "meer"}
        and tokens & {"form", "formed", "create", "created", "cause", "causes",
                      "why", "how", "entstehen", "entsteht", "warum", "wie"}
        and not (tokens & {"tsunami", "tsunamis", "tidal", "tides",
                           "rogue", "earthquake", "erdbeben", "swell"})):
        return "ocean_waves"
    if (tokens & {"lava", "lavastrom"}
        and tokens & {"ocean", "sea", "seawater", "meer", "meerwasser"}
        and tokens & {"hits", "hit", "meets", "meet", "enter", "enters",
                      "touch", "touches", "flows", "flow", "fließt", "passiert"}):
        return "lava_ocean_entry"
    if (tokens & {"ocean", "sea", "meer", "meereswellen"}
        and tokens & {"glow", "glows", "glowing", "shine", "shines", "shining",
                      "leuchtet", "leuchten", "bioluminescence", "biolumineszenz"}
        and tokens & {"blue", "night", "nachts", "blau", "bioluminescence", "biolumineszenz"}
        and not tokens & {"sunlight", "daytime", "sunset", "reflection", "reflections"}):
        return "ocean_glow_bioluminescence"
    if (("badezimmerspiegel" in raw or
         ("spiegel" in raw and ("bad" in tokens or "dusche" in raw)))
        and ("beschl" in raw or "dampf" in raw or "kondens" in raw)):
        return "mirror_condensation"
    if (("mirror" in tokens or "mirrors" in tokens)
        and ("bathroom" in tokens or "shower" in tokens)
        and ("fog" in raw or "steam" in raw or "condens" in raw)):
        return "mirror_condensation"
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
    if scene_count == 3 and kind == "lightning_thunder_delay":
        narration = (
            [
                "Lightning and thunder happen together in a storm.",
                "Light travels much faster than sound, so the flash reaches your eyes first.",
                "The thunder arrives later. A longer delay usually means the lightning is farther away.",
            ] if language == "en" else [
                "Blitz und Donner entstehen bei einem Gewitter praktisch gleichzeitig.",
                "Licht ist schneller als Schall. Deshalb sehen wir den Blitz zuerst.",
                "Den Donner hören wir später. Eine längere Pause bedeutet meist einen weiter entfernten Blitz.",
            ])
    elif scene_count == 3 and kind == "northern_lights_glow":
        narration = (
            [
                "Northern lights glow high in Earth's atmosphere, often near the polar regions.",
                "Energetic electrons follow Earth's magnetic field and collide with oxygen and nitrogen.",
                "Those gases release colorful light, creating the dancing aurora in the night sky.",
            ] if language == "en" else [
                "Nordlichter leuchten hoch in der Atmosphäre, oft nahe den Polargebieten.",
                "Elektronen folgen dem Erdmagnetfeld und stoßen mit Sauerstoff und Stickstoff zusammen.",
                "Dabei entsteht farbiges Licht, das als Polarlicht über den Nachthimmel zieht.",
            ])
    elif scene_count == 3 and kind == "ocean_waves":
        narration = (
            [
                "Most ocean surface waves form when wind transfers energy to the water.",
                "Wave height depends on wind speed, duration, and distance over open water.",
                "Near shore, shallow water makes waves steeper until they break.",
            ] if language == "en" else [
                "Die meisten Meereswellen entstehen, wenn Wind Energie auf das Wasser überträgt.",
                "Die Wellenhöhe hängt von Windstärke, Dauer und der Strecke über Wasser ab.",
                "In Küstennähe werden Wellen durch flaches Wasser steiler und brechen.",
            ])
    elif scene_count == 3 and kind == "lava_ocean_entry":
        narration = (
            [
                "Glowing lava enters the ocean and turns seawater into billowing clouds of steam.",
                "The lava cools and shatters into rock fragments while acidic gases may rise with the plume.",
                "Sometimes unstable new coastal land collapses, triggering dangerous steam explosions at the ocean entry.",
            ] if language == "en" else [
                "Glühende Lava fließt ins Meer und lässt große Dampfwolken aufsteigen.",
                "Beim Abkühlen zerbricht Lava in Gesteinsstücke. Die Wolken können saure Gase enthalten.",
                "Manchmal stürzt frisch entstandene Lavaküste ein und löst gefährliche Dampfexplosionen aus.",
            ])
    elif scene_count == 3 and kind == "ocean_glow_bioluminescence":
        narration = (
            [
                "Some ocean waves glow bright blue at night because of tiny marine organisms.",
                "Certain plankton emit flashes when the water moves.",
                "This natural light is called bioluminescence, produced by a chemical reaction in living organisms.",
            ] if language == "en" else [
                "Manche Meereswellen leuchten nachts blau, weil winzige Meeresorganismen Licht erzeugen.",
                "Bestimmtes Plankton leuchtet auf, wenn sich das Wasser bewegt.",
                "Das heißt Biolumineszenz: Licht entsteht durch chemische Reaktionen in Lebewesen.",
            ])
    elif scene_count == 3 and kind == "mirror_condensation":
        if language == "de":
            narration = [
                "Beim Duschen verdunstet warmes Wasser. Die Luft im Bad wird feucht.",
                "Der Spiegel ist kühler. Wasserdampf wird dort zu winzigen Wassertropfen.",
                "Diese Tropfen beschlagen die Oberfläche und machen das Spiegelbild unscharf.",
            ]
        else:
            narration = [
                "Warm shower water evaporates, making the bathroom air more humid.",
                "The cooler mirror causes water vapor to condense into tiny droplets.",
                "These droplets cover the glass and make your reflection look foggy.",
            ]
    elif scene_count == 3:
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
        "image_prompt": "", "main_character": "", "object": ("volcano" if kind in ("volcanic_island", "lava_ocean_entry") else
                    "hurricane" if kind == "hurricane_eye" else
                    "wave" if kind in ("ocean_waves", "ocean_glow_bioluminescence") else
                    "mirror" if kind == "mirror_condensation" else
                    "lightning" if kind == "lightning_thunder_delay" else "aurora"),
        "action": "ambient", "location": "", "time": "",
        "visual_search_query": ("lava entering ocean steam" if kind == "lava_ocean_entry" else
                                   "volcano erupting" if kind == "volcanic_island" else
                                   "hurricane satellite clouds" if kind == "hurricane_eye" else
                                   "ocean waves" if kind == "ocean_waves" else
                                   "bioluminescent ocean waves" if kind == "ocean_glow_bioluminescence" else
                                   "foggy bathroom mirror" if kind == "mirror_condensation" else
                                   "lightning storm" if kind == "lightning_thunder_delay" else
                                   "aurora borealis"),
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
