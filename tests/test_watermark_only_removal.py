"""Hide BOTH upper hook title and PurffleStudios watermark in all future videos.

Keep spoken narration, synchronized word-highlight captions, topic footage,
and the progress indicator intact. The large title/rules must stay absent.
"""
import ast
from pathlib import Path

from purffle_shorts.config import Settings

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = (
    "videos.yml",
    "daily-life-five-20261118.yml",
    "one-german-bathroom-mirror-20261118.yml",
    "one-video-volcanic-island-20261118.yml",
)


def test_watermark_and_opening_title_disabled_without_touching_word_captions():
    settings = Settings(channel_name="PurffleStudios",
                        watermark="none", hook_overlay=False,
                        caption_emphasis=True, progress_bar=True)
    assert settings.watermark_text == ""
    assert settings.hook_overlay is False
    assert settings.caption_emphasis is True
    assert settings.progress_bar is True


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
