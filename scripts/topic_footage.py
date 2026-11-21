"""Reusable topical visual anchors for V3, independent of the LLM response.

The user-facing topic is authoritative. LLM proposals are suggestions only.
A concept lexicon handles common cross-vocabulary stock labels, e.g.
'northern lights' vs 'aurora borealis', and 'beaches' vs 'beach'.
Always use independent media metadata, license, quality, motion and CLIP checks.
"""
from __future__ import annotations

import re

STOP = frozenset(
    "what when where why which who how is are was were do does did can could "
    "would should will to the a an there this that those these from with "
    "without into about inside outside among really again same makes make "
    "some many most very every world biggest powerful happen happens happening "
    "have has had been each much across during even though look looks "
    "looking different because become becomes over under and or for of in "
    "our their your its at on by it you i they".split()
)

# This is a *vocabulary* for general documentary subjects, not a permission
# to synthesize generic filler unrelated to the user's topic.
ALIASES = {
    "aurora": {"aurora", "borealis", "northern", "light", "lights", "polar"},
    "beach": {"beach", "beaches", "shore", "coast", "coastline"},
    "sand": {"sand", "sandy", "volcanic"},
    "hurricane": {"hurricane", "cyclone", "typhoon", "tropical", "storm",
                  "eyewall", "ocean", "sea", "winds"},
    "wave": {"wave", "waves", "ocean", "sea", "surf"},
    "glacier": {"glacier", "glaciers", "ice", "iceberg"},
    "iceberg": {"iceberg", "icebergs", "ice", "glacier", "calving"},
    "meteor": {"meteor", "meteors", "meteorite", "fireball", "shooting", "star"},
    "volcano": {"volcano", "volcanoes", "volcanic", "lava", "eruption"},
    "waterfall": {"waterfall", "waterfalls", "cascade", "falls"},
    "dolphin": {"dolphin", "dolphins", "porpoise"},
    "fog": {"fog", "foggy", "mist", "haze"},
    "lightning": {"lightning", "thunderstorm", "thunder", "storm"},
    "forest": {"forest", "woods", "trees", "tree"},
    "desert": {"desert", "dunes", "sand"},
    "ocean": {"ocean", "sea", "marine", "underwater"},
    "snow": {"snow", "snowfall", "snowing", "blizzard"},
    "mountain": {"mountain", "mountains", "peak", "cliff"},
    "city": {"city", "cities", "town", "urban", "streets"},
    "river": {"river", "rivers", "stream"},
    "moon": {"moon", "lunar"},
    "star": {"star", "stars", "starlight", "galaxy", "sky"},
    "rain": {"rain", "rainfall", "storm", "raindrops"},
    "cave": {"cave", "caves", "cavern"},
    "island": {"island", "islands", "coast"},
    "mirror": {"mirror", "mirrors", "spiegel", "badezimmerspiegel", "bathroom", "shower", "dusche"},
    "shower": {"shower", "showers", "dusche", "duschen", "bathroom"},

}


# Safe real-camera subjects for entirely new topics when the LLM is absent.
# This is NOT a license to show generic scenery for an abstract topic: a
# subject must literally appear in the user's topic before it can be seeded.
FILMABLE_SUBJECTS = frozenset("""
    cat dog bee ant butterfly bird horse elephant lion tiger penguin turtle
    shark whale octopus frog fish coral snail flower sunflower mushroom
    tornado tsunami earthquake geyser rainbow sunset sunrise iceberg meteor
    train tram bus airplane aircraft helicopter rocket spacecraft ship boat
    bicycle motorcycle car factory robot computer laptop smartphone
    telescope microscope bridge building dam castle pyramid monument
    mirror bathroom shower
""".split())


# Minimal fallback vocabulary for frequent German titles. These translate only
# explicitly named visible subjects; abstract science still requires real
# topic-grounded LLM proposals, never random filler.
GERMAN_FILMABLE = {
    "bus": "bus", "busse": "bus",
    "badezimmerspiegel": "mirror", "spiegel": "mirror",
    "dusche": "shower", "duschen": "shower",
    "biene": "bee", "bienen": "bee",
    "katze": "cat", "katzen": "cat",
    "hund": "dog", "hunde": "dog",
    "zug": "train", "züge": "train", "zuege": "train",
    "auto": "car", "autos": "car",
    "flugzeug": "airplane", "flugzeuge": "airplane",
    "rakete": "rocket", "raketen": "rocket",
    "erdbeben": "earthquake",
    "schildkröte": "turtle", "schildkröten": "turtle",
    "vogel": "bird", "vögel": "bird", "voegel": "bird",
    "fisch": "fish", "fische": "fish",
    "ameise": "ant", "ameisen": "ant",
    "schmetterling": "butterfly", "schmetterlinge": "butterfly",
    "regenbogen": "rainbow",
    "hai": "shark", "haie": "shark",
    "wal": "whale", "wale": "whale",
    "delfin": "dolphin", "delfine": "dolphin",
}


def words(value: str) -> set[str]:
    """Light morphological normalization without remote NLP dependencies."""
    out = set()
    for word in re.findall(r"[a-zäöüß]+", str(value).lower()):
        if len(word) < 3:
            continue
        if word == "buses":
            word = "bus"
        elif word.endswith("ies") and len(word) > 5:
            word = word[:-3] + "y"
        elif word.endswith("oes") and len(word) > 5:
            word = word[:-2]
        elif word.endswith(("ches", "shes", "xes", "zes")) and len(word) > 5:
            word = word[:-2]
        elif word.endswith("s") and not word.endswith(("ss", "us", "is")) and len(word) > 3:
            word = word[:-1]
        out.add(word)
    return out


def subject_terms(topic: str) -> set[str]:
    basic = words(topic) - STOP
    expanded = set(basic)
    expanded.update(GERMAN_FILMABLE[word] for word in basic
                    if word in GERMAN_FILMABLE)
    # Each group must be *activated* by a concrete word in the original title;
    # don't add the entire natural-world dictionary to every query.
    for synonyms in ALIASES.values():
        normalized = set().union(*(words(w) for w in synonyms))
        if normalized & basic:
            expanded.update(normalized)
    return expanded


def related_to_topic(topic, obj, query, existing_subjects=()):
    """The *visible object* must be related, not just a word in the query.

    A proposal for 'lightning splits island' has the word 'island' but
    the subject lightning is unrelated to how volcanic islands emerge.
    Avoid treating that textual coincidence as visual-topic evidence.
    """
    wanted = subject_terms(topic)
    object_words = words(obj)
    query_words = words(query)
    if not wanted or not object_words or not query_words:
        return False
    if wanted & object_words:
        return True
    # A contextual mountain/sky/cloud/sea shot is acceptable only when its
    # actual QUERY still includes the requested primary topic subject.
    scenery_context = words("sky clouds cloud coastline seashore ocean sea "
                            "mountains mountain horizon waves wave coastline")
    if object_words <= scenery_context and query_words & wanted:
        return True
    approved = set().union(*(words(x) for x in existing_subjects))
    return bool(object_words & approved and query_words & wanted)


def is_lava_ocean_topic(topic: str) -> bool:
    """Only the literal lava-meeting-seawater topic, not every ocean explainer."""
    t = words(topic)
    return bool(t & {"lava", "magma", "lavastrom"} and
                t & {"ocean", "sea", "seawater", "meer", "meerwasser"})


def lava_subject_in_metadata(metadata: str) -> bool:
    """Reject unrelated generic ocean footage for explicit lava-ocean videos.

    This is a necessary metadata gate, not proof of the visible action.
    Licensed motion, native crop and CLIP verification still run afterward.
    """
    text = str(metadata or "").casefold()
    if any(term in text for term in ("lava lamp", "lava lamps", "molten chocolate")):
        return False
    return bool(words(text) & {"lava", "volcano", "volcanoes", "volcanic", "eruption", "magma"})


def is_glowing_ocean_topic(topic: str) -> bool:
    """Only ocean/sea bioluminescence, not ordinary waves or reflections."""
    t = words(topic)
    return (bool(t & {"ocean", "sea", "meer"}) and
            bool(t & {"glow", "glowing", "bioluminescence", "leuchtet",
                       "glows", "leuchten"}) and
            bool(t & {"blue", "night", "blau", "nachts", "bioluminescence"}))


def bioluminescence_visible_in_metadata(metadata: str) -> bool:
    """Independent provider terminology is necessary, not proof of pixels."""
    value = " ".join(str(metadata).casefold().replace("-", " ").split())
    return any(term in value for term in (
        "bioluminescen", "bioluminescent", "glowing plankton",
        "glowing ocean", "glowing sea", "blue glowing waves",
        "blue glowing water", "plankton glow", "ocean glowing",
        "sea glowing"))


def is_sudden_volcano_eruption_topic(topic: str) -> bool:
    """Only the explainer about a sudden explosive volcanic eruption."""
    t = words(topic)
    return (bool(t & {"volcano", "volcanoes"}) and
            bool(t & {"erupt", "erupts", "eruption"}) and
            bool(t & {"suddenly", "sudden"}) and
            not t & {"island", "underwater", "ocean", "sea"})


def explosive_volcano_evidence_in_metadata(value: str) -> bool:
    """Independent stock title/source clue for a VISIBLE dramatic last shot.

    This is only a preflight necessary-condition test. A live CLIP comparison
    still checks the video crop for a dark ash plume / actual eruption.
    """
    raw = str(value or "").casefold().replace("-", " ").replace("_", " ")
    import re
    terms = set(re.findall(r"[a-z]+", raw))
    return bool(terms & {"erupting", "eruption", "exploding",
                         "explosive", "explosion", "ash", "plume",
                         "blast", "fountain", "lava"})


def explosive_volcano_last_shot_prompts():
    return {
        "subject": "active_volcanic_eruption",
        "positive": ("A real volcanic eruption with bright erupting lava "
                     "and thick smoke or ash billowing from an active crater."),
        "negatives": (
            "A calm green mountain with wispy mist or fog and no eruption.",
            "A distant rocky mountain slope surrounded by clouds with no molten lava.",
        ),
    }


def is_steel_ship_floating_topic(topic: str) -> bool:
    """Narrow scope: a flotation explainer, not shipwrecks or submarines."""
    terms = words(topic)
    return (bool(terms & {"steel", "stahl", "stahlschiff"})
            and bool(terms & {"ship", "schiff", "stahlschiff"})
            and bool(terms & {"float", "floating", "floats", "schwimmen", "schwimmt"})
            and not terms & {"submarine", "wreck", "sink", "sinking", "capsize"})


def contradicts_floating_ship(topic: str, candidate_description: str) -> bool:
    """Reject clearly non-floating ships using independent provider metadata.

    Never infer the status of an unlabeled ship from filename alone.
    This rejects explicit wreck/beached/drydock stock, irrespective of its
    aesthetic score, for a subject that is about ships *afloat*.
    """
    if not is_steel_ship_floating_topic(topic):
        return False
    text = str(candidate_description or "").casefold().replace("-", " ").replace("_", " ")
    return bool(re.search(
        r"\b(abandoned|beached|shipwreck|shipwrecked|wrecked|wreckage|"
        r"dry\s*dock|grounded vessel|stranded ship)\b", text))


def opening_subject_prompts(topic: str):
    """Positive/negative captions for a comparative local CLIP opening screen.

    This is a *heuristic* object-prominence screen, not a detector or a
    promise of audience retention. Only clear filmable subjects are covered.
    The caller must check the actually rendered 9:16 crop, not full landscape.
    """
    t = words(topic)
    if t & {"ocean", "sea"} and t & {"glow", "glowing", "blue", "bioluminescence"} and t & {"glow", "glowing", "bioluminescence"}:
        return {
            "subject": "blue_bioluminescent_water",
            "positive": "Real sea waves glowing bright electric blue at night, bioluminescent water shining along the dark shore.",
            "negatives": (
                "Ordinary unlit black ocean waves under the night sky.",
                "Daytime sea waves and reflections from the cloudy sky.",
            ),
        }
    if ("northern" in t and "light" in t) or "aurora" in t:
        return {
            "subject": "visible_aurora",
            "positive": "Bright green colorful aurora borealis curtains clearly moving across the dark night sky.",
            "negatives": (
                "Ordinary dark starry night sky without colorful glowing lights.",
                "A cloudy twilight sky with mountains and no aurora.",
            ),
        }
    if is_steel_ship_floating_topic(topic):
        return {
            "subject": "floating_cargo_ship",
            "positive": "A large cargo container ship prominently visible on the water, filling the camera frame.",
            "negatives": (
                "A wide empty seascape with blue waves, a horizon and cloudy sky.",
                "An empty port waterfront showing the ocean without a vessel.",
            ),
        }
    categories = [
        ({"lightning"}, "lightning",
         "A bright visible bolt of lightning striking in a stormy sky.",
         "Dark gray storm clouds moving across the sky without a lightning flash."),
        ({"volcano", "volcanic", "lava"}, "volcano",
         "A clearly visible volcano eruption, red lava flowing from the crater.",
         "An ordinary rocky mountain landscape with blue sky."),
        ({"iceberg"}, "iceberg",
         "An enormous white iceberg floating clearly visible in dark blue seawater.",
         "A wide seascape with distant mountains and open water."),
        ({"meteor", "meteorite"}, "meteor",
         "A bright meteor fireball with a glowing trail in the night sky.",
         "A dark starry sky with no visible moving fireball."),
        ({"turtle"}, "sea_turtle",
         "A sea turtle clearly visible underwater, swimming near the camera.",
         "A blue underwater ocean scene with only water and coral reef."),
        ({"shark"}, "shark",
         "A large shark prominently visible underwater swimming through blue water.",
         "An empty underwater blue ocean environment without animals."),
        ({"whale"}, "whale",
         "A very large whale visibly breaching the sea surface with a splash.",
         "An empty ocean surface covered in waves and white sea foam."),
        ({"waterfall"}, "waterfall",
         "A tall beautiful waterfall clearly visible with moving water or ice.",
         "A rocky mountain landscape and forest without waterfalls."),
        ({"wave"}, "wave",
         "A huge breaking ocean wave with towering white surf filling the frame.",
         "Calm flat open sea under a blue sky with a distant horizon."),
        ({"ship"}, "ship",
         "A large ship clearly visible sailing on the sea, filling much of the frame.",
         "A wide open empty sea horizon under a cloudy sky."),
    ]
    for triggers, name, positive, negative in categories:
        if t & triggers:
            return {
                "subject": name, "positive": positive, "negatives": (negative,)
            }
    return None


def deterministic_stock_shots(topic: str):
    """Grounded seed shots prevent a nonsense/empty LLM reply from ending work
    *before searching the providers*. Never assert footage was found here.

    The high-specificity phrase is kept in each query: do not replace aurora
    with unrelated sky shots or black sand with arbitrary beaches.
    """
    t = words(topic)
    if is_lava_ocean_topic(topic):
        # #77 incorrectly picked four generic ocean clips; the visual hook
        # must show lava/volcanic activity or fail before spending on voice.
        choices = [
            ("lava", "lava flowing into ocean"),
            ("lava", "lava ocean entry"),
            ("lava", "volcanic lava coastline"),
            ("volcano", "lava sea steam eruption"),
            ("lava", "lava flow near water"),
            ("volcano", "volcano lava eruption"),
            ("lava", "molten lava flow"),
        ]
    elif is_glowing_ocean_topic(topic):
        # Production #85 selected plain "underwater sea" as alleged blue
        # bioluminescence. Never search generic daytime or dark water as
        # though it showed glowing plankton.
        choices = [
            ("ocean", "bioluminescent ocean waves"),
            ("ocean", "glowing ocean blue night"),
            ("ocean", "bioluminescence glowing sea"),
            ("ocean", "glowing plankton ocean"),
            ("ocean", "blue glowing waves beach"),
        ]
    elif "northern" in t and ("light" in t or "aurora" in t):
        choices = [
            ("aurora", "aurora borealis"),
            ("aurora", "northern lights timelapse"),
            ("aurora", "aurora night sky"),
            ("aurora", "aurora over mountains"),
            ("aurora", "green northern lights"),
        ]
    elif "lightning" in t and "thunder" in t:
        # Filmable lightning, not random generic storm scenery or an
        # impossible visual representation of the speed of sound.
        choices = [
            ("lightning", "lightning storm"),
            ("lightning", "lightning strikes night sky"),
            ("lightning", "lightning flashes thunderstorm"),
            ("lightning", "lightning clouds night"),
            ("lightning", "thunderstorm lightning"),
        ]
    elif is_steel_ship_floating_topic(topic):
        # #84: generic "ship outdoors" ranked a mostly-empty seascape first,
        # then an abandoned shipwreck. Search for a visible FLOATING vessel.
        choices = [
            ("ship", "cargo ship sailing at sea"),
            ("ship", "container ship floating water"),
            ("ship", "cargo freighter side view waterline"),
            ("ship", "container ship moving ocean"),
            ("ship", "large cargo ship harbor"),
            ("ship", "ship hull ocean side view"),
            ("ship", "loaded container ship sailing"),
        ]
    elif "whale" in t and (t & {"jump", "leap", "breach", "breaching"}):
        choices = [
            ("whale", "whale breaching ocean"),
            ("whale", "humpback whale jumping"),
            ("whale", "whale jumping sea"),
            ("whale", "humpback whale surface"),
            ("whale", "whale ocean close up"),
        ]
    elif "shark" in t:
        choices = [
            ("shark", "shark swimming underwater close up"),
            ("shark", "shark swimming ocean"),
            ("shark", "shark underwater"),
            ("shark", "shark close up sea"),
        ]
    elif "volcano" in t and not "island" in t:
        choices = [
            ("volcano", "volcano erupting lava"),
            ("lava", "molten lava flow volcano"),
            ("volcano", "volcano eruption close up"),
            ("volcano", "volcano explosive eruption ash plume"),
            ("volcano", "volcano aerial eruption"),
        ]
    elif "iceberg" in t:
        choices = [
            ("iceberg", "iceberg floating ocean"),
            ("iceberg", "iceberg drifting sea"),
            ("glacier", "glacier ice calving"),
            ("iceberg", "iceberg sea aerial"),
            ("iceberg", "iceberg breaking ice"),
        ]
    elif "meteor" in t or "meteorite" in t:
        # Actual meteors only: not CGI or unrelated generic night skies.
        choices = [
            ("meteor", "meteor night sky"),
            ("meteor", "meteor fireball night"),
            ("meteor", "meteor shower night"),
            ("meteor", "meteor entering atmosphere"),
            ("meteor", "shooting star meteor"),
        ]
    elif "turtle" in t:
        # Real sea-turtle footage is illustrative, not evidence of sleeping.
        choices = [
            ("turtle", "sea turtle underwater"),
            ("turtle", "sea turtle swimming"),
            ("turtle", "turtle underwater ocean"),
            ("turtle", "sea turtle close up"),
            ("turtle", "marine turtle diving"),
        ]
    elif "black" in t and "sand" in t:
        choices = [
            ("sand", "black sand beach"),
            ("sand", "black volcanic sand"),
            ("beach", "black sand coastline"),
            ("beach", "black sand waves"),
            ("sand", "black sand shore"),
        ]
    elif ("mirror" in t or "badezimmerspiegel" in t or "spiegel" in t) and (
            "beschlägt" in t or "fog" in t or "foggy" in t or "bathroom" in t):
        choices = [
            ("mirror", "foggy bathroom mirror"),
            ("mirror", "bathroom mirror steam"),
            ("mirror", "wiping foggy mirror"),
            ("shower", "hot shower bathroom"),
            ("mirror", "bathroom mirror condensation"),
            ("shower", "water running shower"),
        ]
    elif ("volcano" in t or "volcanic" in t) and "island" in t:
        # Distinguish an island forming from the unrelated phenomenon of
        # volcanic lightning (old generic fallback misled #71 narration).
        choices = [
            ("volcano", "volcano erupting"),
            ("lava", "volcanic lava"),
            ("island", "volcanic island coastline"),
            ("volcano", "volcano landscape"),
            ("lava", "lava flow ocean coast"),
        ]
    elif "hurricane" in t or "cyclone" in t:
        # Actual cyclone imagery is searched *before* ordinary scenery, which
        # is then only supporting B-roll, not a claim to show the storm's eye.
        choices = [
            ("hurricane", "hurricane satellite clouds"),
            ("hurricane", "hurricane storm footage"),
            ("cyclone", "tropical cyclone satellite"),
            ("hurricane", "hurricane eyewall clouds"),
            ("hurricane", "hurricane over ocean"),
            ("storm", "tropical storm ocean waves"),
        ]
    else:
        # Generic subject-driven query generation across many natural topics.
        # No new science or event claims; topic concepts themselves remain.
        concepts = [name for name, synonyms in ALIASES.items()
                    if words(name) & t]
        if concepts:
            primary = concepts[0]
            phrases = [f"{primary} nature", f"{primary} close up",
                       f"{primary} landscape", f"{primary} footage"]
        else:
            # For filmable subjects outside the curated documentary vocabulary,
            # query the named subject itself before asking Groq for alternatives.
            # Reject opaque/abstract words instead of choosing random stock.
            title_words = re.findall(r"[a-zäöüß]+", str(topic).casefold())
            primary = None
            for raw in title_words:
                primary = GERMAN_FILMABLE.get(raw)
                if primary:
                    break
                variants = sorted(words(raw) & FILMABLE_SUBJECTS)
                if variants:
                    primary = variants[0]
                    break
            if not primary:
                return []
            phrases = [f"{primary} footage", f"{primary} close up",
                       f"{primary} outdoors", f"{primary} documentary"]
        choices = [(primary, q) for q in phrases]
    return [dict(main_character="", object=obj, action="ambient",
                 location="", time="", visual_search_query=query)
            for obj, query in choices]
