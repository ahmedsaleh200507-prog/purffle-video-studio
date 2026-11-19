"""Regression: avoid Python 3.12 PyAV 19 metadata_errors incompatibility.

Live voice-only smoke #6 used PyAV 18.1.0 and succeeded;
English ocean-wave render #1 resolved PyAV 19.0.2 and crashed
inside faster-whisper's av.open(..., metadata_errors="ignore").
These assertions ensure every real production entrypoint pins the
same working decoder, without exposing private voice recordings.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = (
    "videos.yml",
    "daily-life-five-20261118.yml",
    "one-german-bathroom-mirror-20261118.yml",
    "one-video-volcanic-island-20261118.yml",
    "one-english-ocean-waves-20261119.yml",
)


def test_all_english_production_workflows_pin_compatible_pyav():
    for filename in WORKFLOWS:
        body = (ROOT / ".github" / "workflows" / filename).read_text()
        assert "'faster-whisper==1.2.1' 'resemblyzer==0.1.4' 'av==18.1.0'" in body, filename
        assert "assert av.__version__ == '18.1.0'" in body, filename
        assert "secrets.PURFFLE_REFERENCE_OPUS_B64" in body, filename
        assert "WATERMARK: none" in body, filename


def test_single_english_ocean_video_must_be_real_and_failed_runs_fail():
    body=(ROOT / ".github" / "workflows" / "one-english-ocean-waves-20261119.yml").read_text()
    assert "INPUT_1: 'en|Why Do Ocean Waves Form?'" in body
    assert "name: create-videos | One English ocean waves video" in body
    assert "python scripts/reference_voice_smoke.py" in body
    assert "python scripts/batch.py" in body
    assert "if row.get('status') != 'ok':" in body
    assert "WATERMARK: none" in body
    assert "RESOLUTION: 720x1280" in body
