"""Only the default PurffleStudios watermark is disabled.

Keep the existing hook title, synchronized word-highlight captions,
progress indicator and every non-watermark visual intact.
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


def test_watermark_none_hides_channel_name_without_affecting_hook_or_captions():
    settings = Settings(channel_name="PurffleStudios",
                        watermark="none", hook_overlay=True,
                        caption_emphasis=True, progress_bar=True)
    assert settings.watermark_text == ""
    assert settings.hook_overlay is True
    assert settings.caption_emphasis is True
    assert settings.progress_bar is True


def test_renderer_explicitly_disables_only_watermark():
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
    assert "hook_overlay=False" not in text  # The hook title must not be removed.


def test_every_production_workflow_keeps_word_captions_and_hides_only_brand_text():
    for filename in WORKFLOWS:
        workflow = (ROOT / ".github" / "workflows" / filename).read_text(encoding="utf-8")
        assert "      WATERMARK: none" in workflow, filename
        assert "      CAPTION_EMOJI: 'false'" in workflow, filename
        assert "HOOK_OVERLAY: 'false'" not in workflow, filename
        assert "CAPTION_STYLE: none" not in workflow, filename
