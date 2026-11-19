"""A real incident: 334 rejections and 0/3 stock clips on run 44415362323.

Provider video tags often include 'mirror' or a bath/shower but do not use
our internal non-camera verb 'ambient'. Require real visible subject matches.
Never bypass independent image, motion, native resolution or license gates.
"""
import pytest

from media_validation import SceneMatcher, SceneSpec, ValidationError


@pytest.mark.parametrize("query,object_name,metadata", [
    ("foggy bathroom mirror", "mirror",
     "Mirror reflection inside a tiled bath with hot fog on the glass"),
    ("bathroom mirror steam", "mirror",
     "Bathroom mirror above a sink"),
    ("wiping foggy mirror", "mirror",
     "A close up of a mirror with condensation"),
    ("hot shower bathroom", "shower",
     "Water running from showerhead in a bathroom"),
    ("water running shower", "shower",
     "Bathroom shower with flowing water"),
])
def test_actual_domestic_scene_metadata_can_reach_frame_verifier(query, object_name, metadata):
    spec = SceneSpec(main_character="", object=object_name, action="ambient",
                     visual_search_query=query)
    assert SceneMatcher.validate_metadata(spec, metadata) >= .25


@pytest.mark.parametrize("query,object_name,metadata", [
    ("foggy bathroom mirror", "mirror", "Mountain mist over ocean waves"),
    ("hot shower bathroom", "shower", "Geminids meteor shower over the stars"),
    ("water running shower", "shower", "November meteor shower from space"),
    ("hot shower bathroom", "shower", "Golden shower concert rock band"),
    ("foggy bathroom mirror", "mirror", "Shower water running against white tiles"),
])
def test_unrelated_camera_subject_or_ambiguous_shower_rejected(query, object_name, metadata):
    spec = SceneSpec(main_character="", object=object_name, action="ambient",
                     visual_search_query=query)
    with pytest.raises(ValidationError):
        SceneMatcher.validate_metadata(spec, metadata)


def test_actor_action_not_weakened_to_ambient():
    spec = SceneSpec(main_character="woman", object="mirror",
                     action="wiping", visual_search_query="wiping foggy mirror")
    with pytest.raises(ValidationError):
        SceneMatcher.validate_metadata(spec, "Bathroom mirror above sink")


def test_no_implicit_metadata_bypass_after_acceptance():
    from pathlib import Path
    code = (Path(__file__).parents[1] / "scripts" / "studio_runtime.py").read_text()
    assert "self.matcher" in code
    assert "match" in code
    assert "quality" in code
    assert "LicenseValidator.validate" in code
