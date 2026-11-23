"""Real V5 proof: keep evidence-checked speech, fix impossible camera plans."""
import json
from types import SimpleNamespace

from visible_science_repair import visible_context_repair


def story():
    scenes = [
        SimpleNamespace(
            narration="Sunlight scatters as it meets tiny air molecules.",
            object="molecules", action="scattering", main_character="",
            location="atmosphere", time="day",
            visual_search_query="sunlight hitting air molecules",
            search_query="sunlight hitting air molecules",
            image_prompt="original plan",
        ),
        SimpleNamespace(
            narration="Blue light scatters more strongly than red light.",
            object="blue light", action="scattering", main_character="",
            location="sky", time="day",
            visual_search_query="blue light scattering",
            search_query="blue light scattering",
            image_prompt="original plan",
        ),
        SimpleNamespace(
            narration="The sky looks blue as daylight spreads across it.",
            object="sky", action="ambient", main_character="",
            location="outdoors", time="day",
            visual_search_query="blue sky view",
            search_query="blue sky view",
            image_prompt="original plan",
        ),
    ]
    return SimpleNamespace(
        scenes=scenes, title="Why Is the Sky Blue?",
        topic="Why is the sky blue?", description="An educational Short",
    )


def test_real_proof_unfilmable_scenes_get_true_camera_footage_queries():
    original = story()
    revised = visible_context_repair(
        original, "Why is the sky blue?", [1, 2])
    assert revised is not None
    assert revised is not original
    assert [x.narration for x in revised.scenes] == [
        x.narration for x in original.scenes]
    assert revised.scenes[0].object == "sky"
    assert revised.scenes[1].object == "sky"
    assert revised.scenes[0].visual_search_query == "blue sky white clouds"
    assert revised.scenes[1].visual_search_query == "sunlight blue sky clouds"
    assert revised.scenes[2].visual_search_query == "blue sky view"
    assert all(x.main_character == "" for x in revised.scenes)
    assert revised.scenes[0].action == "ambient"
    assert revised.scenes[0].search_query == revised.scenes[0].visual_search_query
    assert json.loads(revised.scenes[1].image_prompt)["object"] == "sky"
    # The originally reviewed science and visual plans remain untouched.
    assert original.scenes[0].object == "molecules"
    assert original.scenes[1].visual_search_query == "blue light scattering"
    assert original.scenes[2].image_prompt == "original plan"


def test_unavailable_slots_accept_report_dicts_and_ignore_out_of_range():
    revised = visible_context_repair(story(), "Why is the sky blue?", [
        {"scene": 1, "status": "unavailable"}, {"scene": 7}, 0, None])
    assert revised is not None
    assert revised.scenes[0].object == "sky"
    assert revised.scenes[1].visual_search_query == "blue light scattering"


def test_dont_turn_real_lava_event_into_unrelated_sky_broll():
    assert visible_context_repair(
        story(), "What happens when lava meets the ocean?", [1, 2]) is None


def test_do_not_override_existing_filmable_sky_plan_or_missing_metadata():
    script = story()
    assert visible_context_repair(
        script, "Why is the sky blue?", [3]) is None
    assert visible_context_repair(
        script, "Why is the sky blue?", []) is None
    script.scenes[0].narration = "An astronaut looks toward Earth."
    assert visible_context_repair(
        script, "Why is the sky blue?", [1]) is None


def test_repair_keeps_entire_title_scene_count_and_speakers():
    sample = story()
    for scene in sample.scenes:
        scene.speaker = "A"
    revised = visible_context_repair(
        sample, "Warum ist der Himmel blau?", [1, 2])
    assert revised.title == sample.title
    assert len(revised.scenes) == len(sample.scenes)
    assert [scene.speaker for scene in revised.scenes] == ["A"] * 3
