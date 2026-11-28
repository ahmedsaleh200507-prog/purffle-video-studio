"""Zero-LLM writer for already source-reviewed, topic-specific science dossiers.

This is not a generic factuality bypass. Only exact pre-existing, narrowly
recognized documentaries can use it. science_sources.screen_narration must
still independently enforce exact approved sentences and official URLs.
Unknown topics retain Groq/Gemini source screening unchanged.
"""


def approved_dossier_draft(topic, language, evidence, *, scene_count=3):
    if getattr(evidence, "method", None) != "curated_editor_reviewed":
        return None
    from fact_checked_topics import verified_documentary_kind, ground_verified_documentary
    from purffle_shorts import script as script_module
    from purffle_shorts.topics import Topic

    kind = verified_documentary_kind(topic)
    if not kind:
        return None
    if scene_count not in (2, 3, 4):
        raise ValueError("curated documentary requires 2–4 factual scenes")
    payload = ground_verified_documentary(
        {"topic": topic}, topic, language, scene_count=scene_count)
    # Uses the already-installed strict structured-scene normalizer, which
    # requires real filmable object/action/query for every factual scene.
    from visual_director import use_story_scene_target
    with use_story_scene_target(scene_count):
        story = script_module.normalize(payload, topic, "facts", language)
    if len(story.scenes) != scene_count:
        raise ValueError("curated dossier scene count does not match storyboard")
    return story, Topic(topic, "manual"), "approved_official_dossier"
