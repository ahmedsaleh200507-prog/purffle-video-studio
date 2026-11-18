"""Test Shorts upload titles without network, stock APIs or video rendering."""
import json
from pathlib import Path

from youtube_metadata import MAX_TITLE, attach_title_to_video, make_short_title, write_batch_titles


def test_english_topic_produces_focused_short_title_without_api(monkeypatch):
    monkeypatch.setenv("PURFFLE_SHORTS_TITLE_AI", "0")
    for topic in (
        "Why Does the Ocean Glow Blue at Night?",
        "What Happens When Lightning Strikes a Volcano?",
        "The Mysterious Island Where Thousands of Snakes Live",
    ):
        title = make_short_title(topic, "en")
        assert 20 <= len(title) <= MAX_TITLE
        assert topic in title
        assert "\n" not in title
        assert title != "YouTube Shorts"


def test_very_long_topic_is_safely_shortened(monkeypatch):
    monkeypatch.setenv("PURFFLE_SHORTS_TITLE_AI", "0")
    title = make_short_title("Why is the ocean so mysterious " + "underwater " * 30, "en")
    assert title
    assert len(title) <= MAX_TITLE
    assert "ocean" in title


def test_no_api_or_empty_ai_response_uses_topic_fallback(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("PURFFLE_SHORTS_TITLE_AI", raising=False)
    assert "Ocean" in make_short_title("Why Does the Ocean Glow Blue at Night?")
    assert make_short_title("", "en").strip()


def test_title_saved_next_to_validated_mp4_and_aggregate(tmp_path, monkeypatch):
    monkeypatch.setenv("PURFFLE_SHORTS_TITLE_AI", "0")
    root = tmp_path
    video = root / "finished" / "video_01" / "render" / "ocean" / "final.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"validated in render_job - fake file for sidecar test")
    metadata = video.parent / "metadata.json"
    metadata.write_text(json.dumps({"title": "An Ocean Mystery"}))
    result = {
        "status": "ok", "index": 1, "language": "en",
        "topic": "Why Does the Ocean Glow Blue at Night?",
        "mp4": str(video), "metadata": str(metadata),
    }
    attached = attach_title_to_video(result)
    title_file = video.parent / "YouTube_Title.txt"
    assert title_file.exists()
    assert title_file.read_text().strip() == attached["youtube_title"]
    assert attached["youtube_title_file"] == str(title_file)
    title_file.write_text("A New Saved Title 🌊\n")
    assert attach_title_to_video(attached)["youtube_title"] == "A New Saved Title 🌊"

    second_video = root / "finished" / "video_02" / "render" / "volcano" / "final.mp4"
    second_video.parent.mkdir(parents=True)
    second_video.write_bytes(b"valid")
    second = attach_title_to_video({
        "status": "ok", "index": 2, "language": "en",
        "topic": "What Happens When Lightning Strikes a Volcano?",
        "mp4": str(second_video),
    })
    failed = {"status": "failed", "index": 3, "topic": "No Footage", "mp4": None}
    txt = write_batch_titles(root, [attached, second, failed]).read_text()
    assert "VIDEO 01" in txt and "VIDEO 02" in txt
    assert "VIDEO 03" not in txt
    assert "A New Saved Title" in txt
    assert "Volcano" in txt
    assert "MP4:" in txt


def test_failed_or_missing_video_never_receives_title(tmp_path, monkeypatch):
    monkeypatch.setenv("PURFFLE_SHORTS_TITLE_AI", "0")
    failed = {"status": "failed", "topic": "Why?", "mp4": None}
    assert attach_title_to_video(failed) is failed
    missing = {"status": "ok", "topic": "Why?", "mp4": str(tmp_path / "missing.mp4")}
    assert "youtube_title" not in attach_title_to_video(missing)
    text = write_batch_titles(tmp_path, [failed, missing]).read_text()
    assert "No validated MP4 titles available yet" in text


def test_german_support_preserved(monkeypatch):
    monkeypatch.setenv("PURFFLE_SHORTS_TITLE_AI", "0")
    title = make_short_title("Warum leuchtet das Meer nachts?", "de")
    assert "Warum leuchtet" in title
    assert len(title) <= MAX_TITLE


def test_bad_ai_response_is_not_accepted(monkeypatch):
    # The local fallback is reliable if the remote model ever returns a
    # hallucinated, unrelated, empty or malformed result.
    import sys
    from types import SimpleNamespace

    class FakeCompletions:
        def create(self, **kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
                content="The Secret of an Unrelated Topic"
            ))])

    fake_client = lambda **kwargs: SimpleNamespace(
        chat=SimpleNamespace(completions=FakeCompletions()))
    monkeypatch.setenv("GROQ_API_KEY", "dummy-for-unit-tests")
    monkeypatch.setenv("PURFFLE_SHORTS_TITLE_AI", "1")
    monkeypatch.setitem(sys.modules, "groq", SimpleNamespace(Groq=fake_client))
    title = make_short_title("Why Does the Ocean Glow at Night?", "en")
    assert "Ocean" in title
    assert "Unrelated" not in title
