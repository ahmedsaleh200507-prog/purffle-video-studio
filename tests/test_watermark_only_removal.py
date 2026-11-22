"""Hide BOTH upper hook title and PurffleStudios watermark in all future videos.

Keep spoken narration, synchronized word-highlight captions, topic footage,
and the progress indicator intact. The large title/rules must stay absent.
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Word-highlight captions belong to Shorts. Long videos intentionally have
# no embedded or burned-in subtitles and provide SRT as a sidecar instead.
WORKFLOWS = ("videos.yml",)


def test_watermark_and_opening_title_disabled_without_touching_word_captions():
    # Fast-smoke installs no upstream purffle_shorts; check production settings
    # directly rather than importing uninstalled upstream dependencies.
    renderer = ROOT / "scripts" / "render_job.py"
    text = renderer.read_text(encoding="utf-8")
    tree = ast.parse(text)
    override_names = {
        keyword.arg: keyword.value.value
        for node in ast.walk(tree) if isinstance(node, ast.Call)
        for keyword in node.keywords if isinstance(keyword.value, ast.Constant)
    }
    assert override_names["watermark"] == "none"
    assert override_names["hook_overlay"] is False
    assert override_names["caption_emoji"] is False
    assert "caption_style='none'" not in text
    assert "progress_bar=False" not in text


def test_renderer_explicitly_disables_watermark_and_all_upper_title_elements():
    renderer = ROOT / "scripts" / "render_job.py"
    tree = ast.parse(renderer.read_text(encoding="utf-8"))
    values = [
        keyword.value.value
        for node in ast.walk(tree) if isinstance(node, ast.Call)
        for keyword in node.keywords
        if keyword.arg == "watermark" and isinstance(keyword.value, ast.Constant)
    ]
    assert "none" in values, "Renderer must override upstream PurffleStudios watermark"
    text = renderer.read_text(encoding="utf-8")
    assert "caption_emoji=False" in text  # Existing caption configuration untouched.
    assert "captions.srt" in text  # Captions are still a required output.
    assert "hook_overlay=False" in text  # No oversized upper heading or decoration.


def test_every_production_workflow_keeps_word_captions_and_hides_brand_text():
    for filename in WORKFLOWS:
        workflow = (ROOT / ".github" / "workflows" / filename).read_text(encoding="utf-8")
        assert "      WATERMARK: none" in workflow, filename
        assert "      CAPTION_EMOJI: 'false'" in workflow, filename
        assert "HOOK_OVERLAY: 'false'" not in workflow, filename
        assert "CAPTION_STYLE: none" not in workflow, filename
