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
    tornado tsunami earthquake geyser rainbow sunset sunrise
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


def deterministic_stock_shots(topic: str):
    """Grounded seed shots prevent a nonsense/empty LLM reply from ending work
    *before searching the providers*. Never assert footage was found here.

    The high-specificity phrase is kept in each query: do not replace aurora
    with unrelated sky shots or black sand with arbitrary beaches.
    """
    t = words(topic)
    if "northern" in t and ("light" in t or "aurora" in t):
        choices = [
            ("aurora", "aurora borealis"),
            ("aurora", "northern lights timelapse"),
            ("aurora", "aurora night sky"),
            ("aurora", "aurora over mountains"),
            ("aurora", "green northern lights"),
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
