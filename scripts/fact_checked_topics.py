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
    "octopus_three_hearts": {
        # Smithsonian Ocean and Horniman Museum support these fixed facts.
        # https://ocean.si.edu/ocean-life/invertebrates/octopuses-squids-and-relatives
        # https://www.horniman.ac.uk/story/fact-file-octopus/
        "en": [
            "An octopus has three hearts, not just one.",
            "Two hearts pump blood through its gills, where the blood picks up oxygen.",
            "The third heart sends oxygen-rich blood through the rest of its body.",
        ],
        "de": [
            "Ein Oktopus hat drei Herzen und nicht nur eines.",
            "Zwei Herzen pumpen Blut durch die Kiemen, wo es Sauerstoff aufnimmt.",
            "Das dritte Herz pumpt sauerstoffreiches Blut durch den übrigen Körper.",
        ],
        "title": {
            "en": "Why Do Octopuses Have Three Hearts?",
            "de": "Warum haben Oktopusse drei Herzen?",
        },
        "description": {
            "en": "Two octopus hearts supply the gills and a third pumps blood around the body.",
            "de": "Zwei Herzen versorgen die Kiemen; das dritte pumpt Blut durch den Körper.",
        },
        "tags": ["octopus", "octopus hearts", "cephalopods", "gills", "marine biology"],
    },
    "volcano_eruption": {
        "en": [
            "Some volcanoes explode. Others pour out rivers of lava. The difference starts underground.",
            "Molten rock called magma rises because it is buoyant and gases exert pressure.",
            "As magma approaches the surface, pressure drops and dissolved gases form expanding bubbles.",
            "If gas escapes easily, lava can flow. If gas is trapped in sticky magma, pressure can drive a violent eruption."
        ],
        "de": [
            "Manche Vulkane explodieren. Andere lassen Lava fließen. Der Unterschied entsteht tief unter der Erde.",
            "Geschmolzenes Gestein, das Magma, steigt durch Auftrieb und Gasdruck nach oben.",
            "Dabei sinkt der Druck. Gelöste Gase bilden Blasen, die sich ausdehnen.",
            "Kann Gas leicht entweichen, kann Lava fließen. Bleibt Gas in zähem Magma gefangen, kann der Druck eine Explosion auslösen."
        ],
        "title": {
            "en": "Why Do Volcanoes Erupt?",
            "de": "Warum brechen Vulkane aus?"
        },
        "description": {
            "en": "USGS explains how gas expansion in rising magma can drive violent volcanic eruptions.",
            "de": "Der sinkende Druck beim Aufstieg von Magma lässt Gase expandieren und kann Vulkanausbrüche antreiben."
        },
        "tags": [
            "volcano",
            "magma",
            "eruption",
            "volcanic gas",
            "USGS"
        ]
    },
    "iceberg_breakup": {
        "en": [
            "A huge iceberg can suddenly crack apart into several drifting pieces.",
            "Fractures grow when stresses and ocean waves bend the floating ice.",
            "Warmer water can also melt ice and worsen existing weak spots.",
            "When cracks spread far enough, chunks break off and drift away."
        ],
        "de": [
            "Ein riesiger Eisberg kann plötzlich in mehrere treibende Teile zerbrechen.",
            "Risse wachsen, wenn Spannungen und Meereswellen das schwimmende Eis biegen.",
            "Wärmeres Wasser kann Eis schmelzen lassen und Schwachstellen verstärken.",
            "Breiten sich Risse weit genug aus, brechen Stücke ab und treiben davon."
        ],
        "title": {
            "en": "Why Do Icebergs Suddenly Break Apart?",
            "de": "Warum zerbrechen Eisberge plötzlich?"
        },
        "description": {
            "en": "NSIDC explains how cracks, waves, and ocean conditions contribute to iceberg breakup and calving.",
            "de": "Risse, Wellen und Meerwasser beeinflussen das Zerbrechen von Eisbergen."
        },
        "tags": [
            "iceberg",
            "calving",
            "ice fractures",
            "polar ocean",
            "NSIDC"
        ]
    },
    "whale_breaching": {
        "en": [
            "A humpback whale bursts out of the sea and lands with a huge splash.",
            "This powerful leap above the surface is known as breaching.",
            "Researchers suspect that the loud splash may help whales communicate over distances.",
            "But scientists are still studying why whales breach in different situations."
        ],
        "de": [
            "Ein Buckelwal springt aus dem Meer und landet mit einem gewaltigen Platschen.",
            "Dieser mächtige Sprung über die Wasseroberfläche heißt Breaching.",
            "Forschende vermuten, dass das laute Platschen Walen bei der Kommunikation helfen kann.",
            "Warum Wale in unterschiedlichen Situationen springen, wird jedoch weiter erforscht."
        ],
        "title": {
            "en": "Why Do Whales Jump Out of the Ocean?",
            "de": "Warum springen Wale aus dem Meer?"
        },
        "description": {
            "en": "Breaching creates a loud splash; researchers suspect communication is one possible reason, but not the only established explanation.",
            "de": "Der Sprung eines Wals erzeugt laute Geräusche. Forschende vermuten Kommunikation als mögliche Ursache."
        },
        "tags": [
            "humpback whale",
            "breaching",
            "whale behavior",
            "marine biology"
        ]
    },
    "shark_ventilation": {
        "en": [
            "Some sharks must keep swimming to breathe, but not all sharks do.",
            "Swimming forces oxygen-rich seawater across their gills.",
            "Sharks that rely on this flow cannot simply stop moving for long.",
            "Other species, like nurse sharks, can pump water over their gills while resting."
        ],
        "de": [
            "Manche Haie müssen zum Atmen weiterschwimmen, aber längst nicht alle.",
            "Beim Schwimmen strömt sauerstoffreiches Meerwasser über ihre Kiemen.",
            "Haie, die diesen Wasserstrom brauchen, können nicht einfach lange stillstehen.",
            "Andere Arten, etwa Ammenhaie, pumpen auch in Ruhe Wasser über ihre Kiemen."
        ],
        "title": {
            "en": "Why Do Some Sharks Have to Keep Swimming?",
            "de": "Warum müssen manche Haie immer weiterschwimmen?"
        },
        "description": {
            "en": "Some sharks depend on swimming to move oxygenated water past their gills; other species can pump water while resting.",
            "de": "Manche Haie müssen Wasser beim Schwimmen über ihre Kiemen leiten, andere können es aktiv pumpen."
        },
        "tags": [
            "shark",
            "gills",
            "ram ventilation",
            "buccal pumping",
            "marine biology"
        ]
    },
    "sea_turtle_rest": {
        "en": [
            "Sea turtles breathe air, but they can rest and sleep underwater.",
            "When active, they must come to the surface for breaths quite often.",
            "While resting, they can stay submerged much longer than when swimming actively.",
            "Eventually, they still need to rise to the surface to breathe."
        ],
        "de": [
            "Meeresschildkröten atmen Luft, können aber unter Wasser ruhen und schlafen.",
            "Wenn sie aktiv sind, müssen sie öfter an die Oberfläche zum Atmen.",
            "In Ruhe können sie viel länger unter Wasser bleiben als beim aktiven Schwimmen.",
            "Schließlich müssen auch sie wieder auftauchen, um Luft zu holen."
        ],
        "title": {
            "en": "Why Do Sea Turtles Sleep Underwater?",
            "de": "Wie schlafen Meeresschildkröten unter Wasser?"
        },
        "description": {
            "en": "NOAA explains that sea turtles breathe air but can rest underwater for extended periods before surfacing.",
            "de": "Meeresschildkröten atmen Luft und können beim Ruhen lange unter Wasser bleiben."
        },
        "tags": [
            "sea turtle",
            "underwater rest",
            "breathing",
            "NOAA",
            "marine reptiles"
        ]
    },
    "waterfall_freezing": {
        "en": [
            "In bitter cold, a waterfall may look frozen while water still runs.",
            "Fine spray and dripping water freeze against surfaces, building up ice.",
            "As the ice grows, liquid water can keep flowing through protected channels.",
            "The outside looks solid, but running water may remain inside or beneath it."
        ],
        "de": [
            "Bei großer Kälte sieht ein Wasserfall manchmal gefroren aus, obwohl Wasser weiterfließt.",
            "Feine Gischt und tropfendes Wasser gefrieren an Oberflächen und bilden Eis.",
            "Während das Eis wächst, kann flüssiges Wasser durch geschützte Kanäle weiterfließen.",
            "Außen wirkt alles fest, doch innen oder darunter kann Wasser strömen."
        ],
        "title": {
            "en": "Why Can a Waterfall Freeze Without Stopping?",
            "de": "Warum kann ein Wasserfall vereisen und weiterfließen?"
        },
        "description": {
            "en": "Studies of waterfall ice explain how frozen surfaces can surround channels of flowing liquid water.",
            "de": "Eis kann die Oberfläche eines Wasserfalls bedecken, während das Wasser im Inneren weiterfließt."
        },
        "tags": [
            "waterfall",
            "ice",
            "freezing",
            "frazil ice",
            "winter physics"
        ]
    },
    "steel_ship_buoyancy": {
        # University Physics / OpenStax, Archimedes' principle:
        # https://openstax.org/books/university-physics-volume-1/pages/14-4-archimedes-principle-and-buoyancy
        # University of Hawai'i, Transportation and Ship Design:
        # https://manoa.hawaii.edu/exploringourfluidearth/physical/navigation-and-transportation/transportation-and-ship-design
        "en": [
            "A solid block of steel sinks in water. But this enormous cargo ship still floats.",
            "Its wide hollow hull holds air and displaces a large volume of water.",
            "That displaced water pushes upward with a buoyant force equal to the water's weight.",
            "The ship floats when buoyancy balances its weight. Extra cargo makes it sit deeper.",
        ],
        "de": [
            "Ein massiver Stahlblock sinkt. Doch dieses riesige Stahlschiff schwimmt.",
            "Sein großer hohler Rumpf enthält Luft und verdrängt viel Wasser.",
            "Das verdrängte Wasser erzeugt eine Auftriebskraft, die dem Gewicht des verdrängten Wassers entspricht.",
            "Das Schiff schwimmt, wenn Auftrieb und Gewicht gleich groß sind. Mit Ladung liegt es tiefer.",
        ],
        "title": {"en": "Why Do Steel Ships Float?",
                  "de": "Warum schwimmen Schiffe aus Stahl?"},
        "description": {
            "en": "Solid steel sinks, but a hollow ship displaces enough water for buoyancy to balance its weight. Learn why cargo pushes ships deeper.",
            "de": "Ein hohles Stahlschiff verdrängt genug Wasser, damit der Auftrieb sein Gewicht trägt. Ladung lässt es tiefer liegen.",
        },
        "tags": ["buoyancy", "steel ships", "displacement", "Archimedes", "physics"],
    },
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
    "northern_lights_dance": {
        # NOAA SWPC explains auroral arcs twist and sway:
        # https://www.spaceweather.gov/phenomena/aurora
        # NASA describes how solar-wind particle flows and magnetic fields
        # continually reshape Earth's shimmering auroral displays:
        # https://science.nasa.gov/sun/auroras/
        "en": [
            "The night sky seems to dance. But those shifting lights aren't clouds.",
            "Charged particles flow along Earth's magnetic field into the upper atmosphere.",
            "Changes in magnetic activity and particle flows make glowing bands twist and sway.",
            "Oxygen and nitrogen release the light, creating curtains that keep changing shape.",
        ],
        "de": [
            "Der Nachthimmel scheint zu tanzen. Doch diese Lichter sind keine Wolken.",
            "Geladene Teilchen folgen dem Erdmagnetfeld bis hoch in die Atmosphäre.",
            "Verändert sich die magnetische Aktivität, bewegen und verdrehen sich die leuchtenden Bänder.",
            "Sauerstoff und Stickstoff geben Licht ab. So verändern die leuchtenden Schleier ihre Form.",
        ],
        "title": {
            "en": "Why Do Northern Lights Dance Across the Sky?",
            "de": "Warum tanzen Nordlichter am Himmel?",
        },
        "description": {
            "en": "Auroral curtains twist and sway as Earth's magnetic activity and energetic particle flows change, according to NOAA and NASA.",
            "de": "Magnetische Aktivität und Teilchenströme lassen die leuchtenden Schleier der Polarlichter ihre Form ändern.",
        },
        "tags": ["northern lights", "aurora dance", "magnetic field", "solar wind", "space weather"],
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


_THREE_SCENE_SOURCE_REVIEWED = {
    "volcano_eruption": {
        "en": [
            "Some volcanoes explode. Others pour out rivers of lava. The difference starts underground.",
            "Magma rises through buoyancy and gas pressure. As pressure drops, gas bubbles expand.",
            "If gas escapes easily, lava can flow. Trapped gas in sticky magma can drive an explosive eruption."
        ],
        "de": [
            "Manche Vulkane explodieren. Andere lassen Lava fließen. Der Unterschied entsteht tief unter der Erde.",
            "Magma steigt durch Auftrieb und Gasdruck auf. Sinkt der Druck, dehnen sich Gasblasen aus.",
            "Kann Gas leicht entweichen, kann Lava fließen. Gefangenes Gas in zähem Magma kann eine Explosion auslösen."
        ]
    },
    "iceberg_breakup": {
        "en": [
            "Enormous icebergs can suddenly break into drifting pieces.",
            "Ocean waves and stresses bend the ice, causing existing cracks to grow.",
            "Melting can deepen weak spots until large chunks finally break away."
        ],
        "de": [
            "Riesige Eisberge können plötzlich in treibende Teile zerbrechen.",
            "Meereswellen und Spannungen biegen das Eis, sodass vorhandene Risse wachsen.",
            "Schmelzen verstärkt Schwachstellen, bis schließlich große Stücke abbrechen."
        ]
    },
    "whale_breaching": {
        "en": [
            "Humpback whales sometimes leap high out of the ocean.",
            "This is called breaching, and the landing creates a huge splash.",
            "Researchers suspect communication is one possible reason, but the causes are not fully understood."
        ],
        "de": [
            "Buckelwale springen manchmal hoch aus dem Meer.",
            "Diese Sprünge heißen Breaching und erzeugen beim Auftreffen laute Geräusche.",
            "Forschende vermuten Kommunikation als einen möglichen Grund, doch die Ursachen sind nicht vollständig geklärt."
        ]
    },
    "shark_ventilation": {
        "en": [
            "Some sharks must swim to breathe, but this is not true for all sharks.",
            "Moving water flows across the gills of sharks that rely on swimming for ventilation.",
            "Other species, including nurse sharks, pump water over their gills while resting."
        ],
        "de": [
            "Manche Haie müssen zum Atmen schwimmen, aber nicht alle.",
            "Beim Schwimmen strömt Wasser über die Kiemen der Arten, die diese Strömung brauchen.",
            "Andere Arten, etwa Ammenhaie, pumpen auch in Ruhe Wasser über ihre Kiemen."
        ]
    },
    "sea_turtle_rest": {
        "en": [
            "Sea turtles breathe air, yet they can rest and sleep underwater.",
            "When actively swimming, they must surface to breathe more often than at rest.",
            "Resting turtles can stay submerged much longer, but eventually they must breathe again."
        ],
        "de": [
            "Meeresschildkröten atmen Luft, können aber unter Wasser ruhen und schlafen.",
            "Beim aktiven Schwimmen müssen sie häufiger zum Atmen auftauchen als in Ruhe.",
            "Ruhende Schildkröten bleiben länger unter Wasser, müssen aber schließlich wieder Luft holen."
        ]
    },
    "waterfall_freezing": {
        "en": [
            "A winter waterfall may look frozen even while water keeps flowing.",
            "Freezing spray and drops build layers of ice across exposed surfaces.",
            "The ice can shelter channels where liquid water continues to flow inside."
        ],
        "de": [
            "Ein Wasserfall kann gefroren aussehen, obwohl das Wasser weiterfließt.",
            "Gefrierende Gischt und Tropfen bilden Eisschichten auf kalten Oberflächen.",
            "Unter dem Eis können geschützte Kanäle bleiben, in denen flüssiges Wasser weiterströmt."
        ]
    }
}

def verified_documentary_kind(topic: str) -> str | None:
    """Recognize exact broad explainers; other topics preserve Groq output."""
    raw = str(topic or "").casefold()
    import re
    text = re.sub(r"[^a-z ]", " ", raw)
    tokens = set(text.split())
    if (tokens & {"octopus", "octopuses", "octopi", "oktopus", "oktopusse"}
        and tokens & {"heart", "hearts", "herzen", "herz"}
        and tokens & {"three", "drei", "3"}
        and not tokens & {"fiction", "game", "movie", "comic"}):
        return "octopus_three_hearts"
    # #105: recognize the German question before collecting unrelated titles.
    if (tokens & {"blitz", "blitze", "blitzen"} and tokens & {"donner"}
        and tokens & {"vor", "zuerst", "sehen", "hoeren", "horen"}
        and not tokens & {"film", "serie", "band"}):
        return "lightning_thunder_delay"
    # Recognize only the ordinary bathroom-mirror explanation, not unrelated
    # uses of a mirror or unrelated fog/weather topics.
    if (tokens & {"steel", "stahl", "stahlschiffe", "stahlschiff"}
        and tokens & {"ship", "ships", "schiff", "schiffe", "stahlschiffe", "stahlschiff"}
        and tokens & {"float", "floats", "floating", "swim", "swims",
                      "schwimmt", "schwimmen", "schwimmt", "schwimmend"}
        and not tokens & {"submarine", "submarines", "u-boot", "u-boats",
                          "sink", "sinking", "capsize", "sinken", "kentern"}):
        return "steel_ship_buoyancy"
    # These narrow source-reviewed explainers are keyed to the 2026-11-20
    # production #85 batch. Unrelated volcanoes, whale diets, other ice
    # questions and all other science still require independent review.
    # Exact generic why/how questions in both languages, not questions
    # about a named volcano, date, location, eruption forecast or impacts.
    if (tokens & {"volcano", "volcanoes", "vulkan", "vulkane"}
            and tokens & {"erupt", "erupts", "eruption", "bricht", "brechen"}
            and (tokens & {"why", "how", "warum", "wieso", "wie", "suddenly", "sudden"})
            and tokens <= {"why","how","do","does","a","the","volcano","volcanoes",
                           "erupt","erupts","eruption","suddenly","sudden",
                           "warum","wieso","wie","ein","der","vulkan","vulkane",
                           "bricht","brechen","aus","plötzlich","pl","tzlich"}):
        return "volcano_eruption"
    if (tokens & {"iceberg", "icebergs"} and
            tokens & {"break", "breaking", "apart", "split", "calving"}):
        return "iceberg_breakup"
    if (tokens & {"whale", "whales"} and
            tokens & {"jump", "jumps", "breach", "breaching", "leap", "leaping"}
            and not tokens & {"ship", "collision", "attack"}):
        return "whale_breaching"
    if (tokens & {"shark", "sharks"} and
            tokens & {"swim", "swimming"} and
            tokens & {"keep", "have", "must", "constantly"}):
        return "shark_ventilation"
    if (tokens & {"turtle", "turtles"} and
            tokens & {"sleep", "rest", "sleeping"} and
            tokens & {"underwater", "water"}):
        return "sea_turtle_rest"
    if (tokens & {"waterfall", "waterfalls"} and
            tokens & {"freeze", "freezes", "frozen", "freezing"} and
            tokens & {"without", "stopping", "still", "stop"}):
        return "waterfall_freezing"
    if ("lightning" in tokens and "thunder" in tokens
            and ({"before", "hearing", "hear", "see", "first"} & tokens)):
        return "lightning_thunder_delay"
    if ((("northern" in tokens and ("lights" in tokens or "light" in tokens))
         or "aurora" in tokens or "auroras" in tokens
         or "nordlichter" in tokens or "polarlichter" in tokens)
         and tokens & {"dance", "dances", "dancing", "moving", "move", "waves",
                       "twists", "sway", "sways", "tanzen", "tanzt", "bewegen"}):
        return "northern_lights_dance"
    if ((("northern" in tokens and ("lights" in tokens or "light" in tokens))
         or tokens & {"aurora", "auroras", "polarlichter", "polarlicht",
                      "nordlichter", "nordlicht"})
         and (tokens & {"glow", "glows", "shine", "shines", "colors",
                        "colour", "why", "warum", "leuchten", "leuchtet", "entstehen",
                        "entsteht", "form", "formed", "formation", "created"})):
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


# Production #91: these approved facts form complete concise two-shot
# explanations. A shorter narration is permitted only if ALL essential facts
# remain accurate and pass the same source-dossier integrity checks.
_TWO_SCENE_SOURCE_REVIEWED = {
    "mirror_condensation": {
        "en": (
            "A bathroom mirror can fog up quickly after a hot shower.",
            "Warm moist air meets cooler glass. Water vapor condenses into tiny droplets that blur the reflection.",
        ),
        "de": (
            "Ein Badezimmerspiegel kann nach einer heißen Dusche schnell beschlagen.",
            "Feuchte warme Luft trifft auf kühles Glas. Wasserdampf kondensiert zu winzigen Tropfen.",
        ),
    },
    "iceberg_breakup": {
        "en": (
            "Huge icebergs drift through the ocean. Some suddenly split apart.",
            "Ocean waves, stress and melting can widen cracks in the ice. Eventually, large chunks break away.",
        ),
        "de": (
            "Riesige Eisberge treiben durch das Meer. Manche zerbrechen plötzlich.",
            "Meereswellen, Spannungen und Schmelzen vergrößern Risse im Eis. Schließlich brechen große Stücke ab.",
        ),
    },
    "whale_breaching": {
        "en": (
            "Humpback whales sometimes leap out of the sea and make an enormous splash.",
            "Scientists do not know every reason why. Communication may be one possible explanation.",
        ),
        "de": (
            "Buckelwale springen manchmal aus dem Meer und verursachen eine riesige Wasserfontäne.",
            "Forschende kennen nicht alle Gründe. Kommunikation könnte eine mögliche Erklärung sein.",
        ),
    },
    "lightning_thunder_delay": {
        "en": (
            "Lightning flashes across the stormy sky before the thunder reaches us.",
            "Light travels faster than sound. That is why we hear thunder after seeing the flash.",
        ),
        "de": (
            "Wir sehen den Blitz am Gewitterhimmel, bevor wir den Donner hören.",
            "Licht bewegt sich schneller als Schall. Deshalb kommt der Donner später bei uns an.",
        ),
    },
    "ocean_glow_bioluminescence": {
        "en": (
            "Some ocean waves glow blue at night because tiny marine organisms emit light.",
            "Moving water can trigger flashes in plankton. That light comes from a chemical reaction.",
        ),
        "de": (
            "Manche Meereswellen leuchten nachts blau, weil winzige Meeresorganismen Licht erzeugen.",
            "Bewegtes Wasser kann Plankton zum Leuchten bringen. Dahinter steckt eine chemische Reaktion.",
        ),
    },
}

_TWO_SCENE_VISUAL_QUERIES = {
    "mirror_condensation": ("foggy bathroom mirror", "bathroom mirror condensation"),
    "iceberg_breakup": ("iceberg floating ocean", "iceberg drifting sea"),
    "whale_breaching": ("humpback whale breaching ocean", "humpback whale swimming ocean"),
    "lightning_thunder_delay": ("lightning storm sky", "lightning clouds storm"),
    "ocean_glow_bioluminescence": ("bioluminescent ocean waves", "glowing plankton ocean"),
}


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
    if scene_count == 2 and kind in _TWO_SCENE_SOURCE_REVIEWED:
        narration = list(_TWO_SCENE_SOURCE_REVIEWED[kind][language])
    elif scene_count == 2 and kind == "northern_lights_glow":
        # #89 had two independently checked HD aurora clips. Avoid demanding
        # three filler shots when two source-reviewed scenes cover the cause.
        narration = (
            [
                "Northern lights glow high in the night sky, especially near the poles.",
                "Electrons collide with oxygen and nitrogen high in Earth's atmosphere. These gases release the colorful aurora light.",
            ] if language == "en" else [
                "Polarlichter leuchten hoch am Nachthimmel, besonders in Polargebieten.",
                "Elektronen stoßen hoch in der Atmosphäre mit Sauerstoff und Stickstoff zusammen. Dabei entsteht das farbige Licht.",
            ])
    elif scene_count == 2 and kind == "lightning_thunder_delay":
        narration = (
            [
                "Lightning and thunder happen together, but light reaches our eyes much faster.",
                "Sound moves slower, so thunder arrives later. A longer delay usually means greater distance.",
            ] if language == "en" else [
                "Blitz und Donner entstehen gleichzeitig, aber Licht erreicht unsere Augen viel schneller.",
                "Schall bewegt sich langsamer, deshalb hören wir Donner später. Eine längere Pause bedeutet meist mehr Entfernung.",
            ])
    elif scene_count == 3 and kind in _THREE_SCENE_SOURCE_REVIEWED:
        narration = list(_THREE_SCENE_SOURCE_REVIEWED[kind][language])
    elif scene_count == 3 and kind == "octopus_three_hearts":
        narration = list(info[language])
    elif scene_count == 3 and kind == "steel_ship_buoyancy":
        narration = (
            [
                "A solid block of steel sinks in water. But this enormous cargo ship still floats.",
                "Its broad hollow hull contains air and pushes a large volume of water aside.",
                "That displaced water pushes upward. When buoyancy balances the ship's weight, it floats, even with cargo.",
            ] if language == "en" else [
                "Ein massiver Stahlblock sinkt. Doch dieses riesige Stahlschiff schwimmt.",
                "Sein breiter hohler Rumpf enthält Luft und verdrängt dadurch viel Wasser.",
                "Das Wasser drückt das Schiff nach oben. Wenn der Auftrieb sein Gewicht ausgleicht, bleibt es über Wasser.",
            ])
    elif scene_count == 3 and kind == "lightning_thunder_delay":
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
    elif scene_count == 3 and kind == "northern_lights_dance":
        narration = (
            [
                "The night sky seems to dance, but these shifting lights aren't clouds.",
                "Charged particles follow Earth's magnetic field and excite gases high in the atmosphere.",
                "As magnetic activity and particle flows change, glowing curtains twist and sway across the sky.",
            ] if language == "en" else [
                "Der Nachthimmel scheint zu tanzen. Doch diese Lichter sind keine Wolken.",
                "Geladene Teilchen folgen dem Erdmagnetfeld und bringen Gase hoch in der Atmosphäre zum Leuchten.",
                "Veränderungen im Magnetfeld und in Teilchenströmen lassen die leuchtenden Schleier tanzen.",
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
        "image_prompt": "", "main_character": "", "object": ("volcano" if kind in ("volcanic_island", "lava_ocean_entry", "volcano_eruption") else
                    "octopus" if kind == "octopus_three_hearts" else
                    "ship" if kind == "steel_ship_buoyancy" else
                    "iceberg" if kind == "iceberg_breakup" else
                    "whale" if kind == "whale_breaching" else
                    "shark" if kind == "shark_ventilation" else
                    "turtle" if kind == "sea_turtle_rest" else
                    "waterfall" if kind == "waterfall_freezing" else
                    "hurricane" if kind == "hurricane_eye" else
                    "wave" if kind in ("ocean_waves", "ocean_glow_bioluminescence") else
                    "mirror" if kind == "mirror_condensation" else
                    "lightning" if kind == "lightning_thunder_delay" else "aurora"),
        "action": "ambient", "location": "", "time": "",
        "visual_search_query": ("lava entering ocean steam" if kind == "lava_ocean_entry" else
                                   "volcano erupting" if kind == "volcanic_island" else
                                   "octopus swimming underwater" if kind == "octopus_three_hearts" else
                                   "cargo ship floating ocean" if kind == "steel_ship_buoyancy" else
                                   "volcano erupting lava" if kind == "volcano_eruption" else
                                   "iceberg breaking ocean" if kind == "iceberg_breakup" else
                                   "humpback whale breaching ocean" if kind == "whale_breaching" else
                                   "shark swimming underwater" if kind == "shark_ventilation" else
                                   "sea turtle swimming underwater" if kind == "sea_turtle_rest" else
                                   "partially frozen waterfall water flowing" if kind == "waterfall_freezing" else
                                   "hurricane satellite clouds" if kind == "hurricane_eye" else
                                   "ocean waves" if kind == "ocean_waves" else
                                   "bioluminescent ocean waves" if kind == "ocean_glow_bioluminescence" else
                                   "foggy bathroom mirror" if kind == "mirror_condensation" else
                                   "lightning storm" if kind == "lightning_thunder_delay" else
                                   "aurora borealis"),
        "emphasis": [], "emoji": "",
    } for sentence in narration]
    if scene_count == 2 and kind in _TWO_SCENE_VISUAL_QUERIES:
        for scene, query in zip(scenes, _TWO_SCENE_VISUAL_QUERIES[kind]):
            scene["visual_search_query"] = query
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
