"""Contract: Purffle Shorts use truthful, attention-first hooks and a real payoff.

No external video, live TTS or third-party YouTube analytics is needed.
All original science/audio/footage checks must stay enabled.
"""
from pathlib import Path
from types import SimpleNamespace

import pytest

from attention_hook import compact_hook_lines
from media_first import VerifiedPalette, footage_prompt


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("topic,expected", [
    ("What Happens When Lava Hits the Ocean?", ["LAVA MEETS OCEAN", "WHAT HAPPENS?"]),
    ("How Do Lighthouses Survive Monster Waves?", ["MONSTER WAVES", "HOW DOES IT SURVIVE?"]),
    ("How Does a Tornado Form Over Water?", ["A TORNADO", "ON WATER?"]),
    ("Why Is Most of an Iceberg Hidden Underwater?", ["ICEBERG MYSTERY", "WHAT'S UNDERWATER?"]),
    ("How Can a Waterfall Freeze?", ["A FROZEN", "WATERFALL?"]),
    ("Why Does the Ocean Glow Blue at Night?", ["THE OCEAN", "CAN GLOW BLUE?"]),
])
def test_short_topic_grounded_on_screen_hooks(topic, expected):
    assert compact_hook_lines(topic) == expected
    assert max(map(len, expected)) <= 30


def test_other_topics_preserve_original_question():
    topic = "Why Do Dolphins Sleep With One Eye Open?"
    assert " ".join(compact_hook_lines(topic)) == topic.upper()


def test_verified_footage_storyboard_has_factual_hook_payoff_and_no_cta():
    palette = VerifiedPalette(
        "What Happens When Lava Hits the Ocean?",
        [
            {"object": "lava", "visual_search_query": "lava ocean steam"},
            {"object": "steam", "visual_search_query": "lava steam cloud"},
            {"object": "rock", "visual_search_query": "volcanic rocks coastline"},
        ],
        [SimpleNamespace(duration=10.0) for _ in range(3)],
        set(),
        [],
    )
    prompt = footage_prompt(palette)
    assert "RETENTION PACING" in prompt
    assert "first scene must begin directly" in prompt
    assert "second scene must deliver" in prompt
    assert "last scene clearly answers" in prompt
    assert "do not invent drama" in prompt
    assert "EXACTLY 3 scenes" in prompt
    assert "lava ocean steam" in prompt


def test_retention_policy_does_not_override_science_footage_or_voice():
    runtime = (ROOT / "scripts" / "studio_runtime.py").read_text(encoding="utf-8")
    renderer = (ROOT / "scripts" / "render_job.py").read_text(encoding="utf-8")
    assert "AUDIENCE RETENTION STORYBOARD" in runtime
    assert "original_prompt(*args, **kwargs)" in runtime
    assert "ground_verified_documentary(" in runtime
    assert "validate_narration_timing(" in renderer
    assert "screen_narration(" in renderer
    assert "enforce_english_reference_only" in renderer
    assert "watermark='none'" in renderer
