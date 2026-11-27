"""Story research context; no ready-made narration or model-invented sources.

Reviewed notes are additional research for the pilot, not approval of new scripts.
Other subjects use actual supplied reference excerpts; no topic-specific writing template.
"""
from fact_checked_topics import ground_verified_documentary, verified_documentary_kind

# Paraphrased research notes, with provenance, rather than sample hooks or scripts.
RESEARCH = {
    "octopus_three_hearts": (
        ("https://ocean.si.edu/ocean-life/invertebrates/octopuses-squids-and-relatives",
         "Octopuses have two gill hearts that move oxygen-poor blood through the gills; "
         "the systemic heart circulates oxygenated blood throughout the body."),
        ("https://www.horniman.ac.uk/story/fact-file-octopus/",
         "During swimming, stiffening muscles can cause the systemic heart to stop functioning. "
         "This describes the systemic heart only; it does not establish why three hearts evolved, "
         "whether the other hearts compensate during swimming, or that the heart stopping causes muscle stiffening."),
    ),
    "northern_lights_glow": (
        ("https://science.nasa.gov/sun/auroras/",
         "Aurora colours provide clues about the emitting gas and approximate altitude, not an exact height measurement. "
         "Excited oxygen produces green at roughly 100–200 km, and red at greater heights. "
         "Nitrogen can emit blue and pink light. Colours may mix. "
         "Energy from the solar wind is transferred into Earth's magnetosphere. "
         "The light is emitted by excited atmospheric gases, not by friction or by the magnetic field itself."),
        ("https://science.nasa.gov/earth/earth-observatory/lights-on-and-over-the-southern-horizon-90507/",
         "Electrons travel along magnetic field lines toward magnetic polar regions. "
         "Collisions transfer energy to oxygen and nitrogen in the upper atmosphere; "
         "the excited gases emit light as they return to lower energy states."),
    ),
}

def story_reference(topic, language, bundle=None):
    """Accept arbitrary topics; use real excerpts or a reviewed dossier, never invented facts."""
    kind=verified_documentary_kind(topic)
    base=ground_verified_documentary({},topic,language)
    rows=[s["narration"] for s in base.get("scenes",[])]
    for url,note in RESEARCH.get(kind,()):
        rows.append(f"Research note ({url}): {note}")
    if bundle is not None:
        for source in bundle.sources:
            excerpt=str(source.get("excerpt","")).strip()
            if excerpt:
                rows.append(f"Reference ({source['url']}): {excerpt}")
    if not rows and bundle is None:
        from science_sources import discover_evidence
        return story_reference(topic,language,discover_evidence(topic,language))
    if not rows:
        raise RuntimeError("No substantive reference material for this topic")
    return "\n".join(rows)
