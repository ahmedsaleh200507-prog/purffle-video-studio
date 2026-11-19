"""Opening hooks are short, highly legible and safe for all Shorts.

The change may modify ONLY opening title visuals. Stock footage validation,
captions, voice identity and existing watermark settings remain unchanged.
"""
from pathlib import Path
from types import SimpleNamespace

import pytest

from attention_hook import (
    accent_words, attention_hook_png, compact_hook_lines, kinetic_hook_filter,
)


def test_lightning_is_hook_not_a_paragraph():
    lines = compact_hook_lines(
        "Why Do We See Lightning Before Hearing Thunder?")
    assert lines == ["LIGHTNING FIRST", "THUNDER LATER", "WHY?"]
    assert {"LIGHTNING", "THUNDER", "WHY?"} <= accent_words(lines)


def test_general_topics_keep_the_question_without_inventing_claims():
    for topic in (
        "Why Do Ocean Waves Form?",
        "Warum beschlägt der Badezimmerspiegel?",
        "How Do Volcanoes Create New Islands?",
        "Why is the sky blue?",
    ):
        lines = compact_hook_lines(topic)
        assert 1 <= len(lines) <= 3
        assert " ".join(lines) == topic.upper()
    assert compact_hook_lines("") == []


def test_animated_hook_changes_only_existing_hook_overlay():
    graph = (
        "[a][cap]overlay=x=0:y=600[vcap];"
        "[vcap][hook]overlay=x=(W-w)/2:y=192:eof_action=pass[vhook];"
        "[vhook][bar]overlay=x=0:y=0[vbar]"
    )
    args = ["-i", "demo.mp4", "-filter_complex", graph, "-map", "[vbar]"]
    changed = kinetic_hook_filter(args)
    assert "48*exp(-7*t)*cos(10*t)" in changed[3]
    assert "[a][cap]overlay=x=0:y=600[vcap]" in changed[3]
    assert "[vhook][bar]overlay=x=0:y=0[vbar]" in changed[3]
    assert args[3] == graph
    assert kinetic_hook_filter(["-i", "demo.mp4"]) == ["-i", "demo.mp4"]
    assert kinetic_hook_filter(["-filter_complex", "null[vout]"]) == [
        "-filter_complex", "null[vout]"]


def test_hook_png_is_transparent_styled_and_portrait_safe(tmp_path):
    Image = pytest.importorskip("PIL.Image")
    output = tmp_path / "hook.png"
    settings = SimpleNamespace(width=720, height=1280, language="en")
    png, y = attention_hook_png(
        settings, None, "Why Do We See Lightning Before Hearing Thunder?",
        output)
    assert png == output and y == 192
    with Image.open(output) as im:
        assert im.mode == "RGBA"
        assert 0 < im.width < settings.width
        assert 0 < im.height < settings.height * .4
        # Not the old large opaque black rectangle.
        assert im.getpixel((0, 0))[3] == 0
        assert im.getpixel((im.width - 1, im.height - 1))[3] == 0
        assert im.getbbox() is not None
