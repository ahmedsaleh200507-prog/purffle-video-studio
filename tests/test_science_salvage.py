"""Regression for the real V5 #102 partial source-check failure."""
import json
from types import SimpleNamespace

from science_salvage import salvage_approved_narration


def draft():
    return SimpleNamespace(
        title="Why Is the Sky Blue?", topic="Why is the sky blue?",
        scenes=[
            SimpleNamespace(narration="Blue light scatters much more than red light.", visual_search_query="blue sky", object="sky"),
            SimpleNamespace(narration="Particles in air can scatter the light that we see.", visual_search_query="air molecules scattering", object="molecules"),
            SimpleNamespace(narration="The sun is always white and fills the whole universe with blue.", visual_search_query="sun rays", object="sun"),
            SimpleNamespace(narration="Sunlight acts like a mirror and never stops shining.", visual_search_query="mirror reflection", object="mirror"),
        ],
    )


def report(tmp_path, supported=(True, True, False, False)):
    p = tmp_path / "science-report.json"
    p.write_text(json.dumps({
        "state": "failed", "method": "model_screened_reference",
        "error": "source passage cannot substantiate all scene claims",
        "sources": [{"id": "wiki-1", "title": "Rayleigh scattering"}],
        "scene_checks": [
            {"scene": n, "source_id": "wiki-1", "supported": yes,
             "quote": ("the amount of scattering is inversely proportional "
                       "to the fourth power of wavelength") if yes else "",
             "reason": "Source-check review; not an instruction"}
            for n, yes in enumerate(supported, 1)]
    }), encoding="utf-8")
    return p


def test_real_proof_2_of_4_source_verified_scenes_can_be_shortened(tmp_path):
    original = draft()
    original.scenes[0].narration += " In the atmosphere, sunlight interacts with tiny particles and molecules."
    original.scenes[1].narration += " The scattered light travels in different directions before reaching our eyes."
    concise = salvage_approved_narration(original, report(tmp_path))
    assert concise is not None
    assert concise is not original
    assert len(concise.scenes) == 2
    assert [scene.narration for scene in concise.scenes] == [
        scene.narration for scene in original.scenes[:2]]
    assert concise.scenes[1].visual_search_query == "air molecules scattering"
    assert len(original.scenes) == 4
    concise.scenes[0].narration = "CHANGED"
    assert original.scenes[0].narration.startswith("Blue light")


def test_salvage_requires_two_explicit_approved_scenes(tmp_path):
    assert salvage_approved_narration(
        draft(), report(tmp_path, (True, False, False, False))) is None
    assert salvage_approved_narration(
        draft(), report(tmp_path, (False, False, False, False))) is None


def test_salvage_refuses_missing_or_fabricated_proof(tmp_path):
    p = report(tmp_path)
    evidence = json.loads(p.read_text())
    evidence["scene_checks"][1]["source_id"] = "unknown"
    p.write_text(json.dumps(evidence))
    assert salvage_approved_narration(draft(), p) is None
    evidence["scene_checks"][1]["source_id"] = "wiki-1"
    evidence["scene_checks"][1]["quote"] = "short"
    p.write_text(json.dumps(evidence))
    assert salvage_approved_narration(draft(), p) is None
    evidence["scene_checks"][1]["quote"] = "a different source quote with enough words"
    evidence["scene_checks"][1]["scene"] = 4
    p.write_text(json.dumps(evidence))
    assert salvage_approved_narration(draft(), p) is None


def test_salvage_never_bypasses_absent_or_nonfailed_review(tmp_path):
    p = report(tmp_path)
    item = json.loads(p.read_text())
    item["state"] = "model_screened_reference"
    p.write_text(json.dumps(item))
    assert salvage_approved_narration(draft(), p) is None
    item["state"] = "failed"
    item["error"] = "science_review_unavailable: strict_groq_http_429"
    p.write_text(json.dumps(item))
    assert salvage_approved_narration(draft(), p) is None


def test_pipeline_tries_salvage_only_after_last_rejection_and_rechecks_source():
    import ast
    from pathlib import Path
    tree = ast.parse(Path("scripts/render_job.py").read_text(encoding="utf-8"))
    parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
    def calls(name):
        return [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Name) and n.func.id == name]
    salvage, = calls("salvage_approved_narration")
    node = salvage
    ancestors = []
    while node in parents:
        node = parents[node]
        ancestors.append(node)
    retry_guard = ast.parse("attempt >= max_attempts - 1", mode="eval").body
    guard = next(n for n in ancestors if isinstance(n, ast.If)
                 and ast.dump(n.test) == ast.dump(retry_guard))
    review, = [n for n in calls("screen_narration") if n.args
               and isinstance(n.args[0], ast.Name) and n.args[0].id == "salvaged"]
    assert review in list(ast.walk(guard))
    assert salvage.lineno < review.lineno
    assert any(isinstance(n, ast.Assign) and isinstance(n.value, ast.Name)
               and n.value.id == "salvaged" and n.lineno > review.lineno
               and any(isinstance(t, ast.Name) and t.id == "screenplay" for t in n.targets)
               for n in ast.walk(guard))
    preflight = [n.lineno for n in ast.walk(tree) if isinstance(n, ast.Assign)
                 and isinstance(n.value, ast.Constant) and n.value.value == "visual_director_preflight"]
    assert review.lineno < min(preflight)


def test_underlength_salvage_does_not_pass(tmp_path):
    assert salvage_approved_narration(draft(),report(tmp_path)) is None
