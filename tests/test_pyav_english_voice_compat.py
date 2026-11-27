"""Keep private English voice decoder pinned in both active video makers.

The old one-off English ocean workflow was archived. These contract tests now
guard the two actively selectable production workflows, not deleted jobs.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ("videos.yml", "long-batch.yml")


def test_all_english_production_workflows_pin_compatible_pyav():
    root=Path(__file__).resolve().parents[1]/'.github/workflows'
    for name in ('videos.yml','long-batch.yml'):
        body=(root/name).read_text()
        assert 'chatterbox-tts' not in body
        assert 'faster-whisper==1.2.1' in body
        assert 'av==14.2.0' in body
        assert 'kokoro==0.9.4' in body
        assert 'secrets.PURFFLE_REFERENCE_OPUS_B64' not in body
        assert 'requirements-dev.txt' in body


def test_active_shorts_workflow_keeps_real_success_checks():
    body = (ROOT / ".github" / "workflows" / "videos.yml").read_text()
    assert "python scripts/batch.py" in body
    assert "WATERMARK: none" in body
    assert "RESOLUTION: 1080x1920" in body
    assert "max-parallel: 1" in body
    assert "fail-fast: false" in body


def test_active_long_documentaries_are_verified_and_not_automatically_published():
    body = (ROOT / ".github" / "workflows" / "long-batch.yml").read_text()
    assert "python scripts/long_video.py" in body
    assert "Verify real 9" in body
    assert "'codec_name']=='h264'" in body
    assert "'codec_name']=='aac'" in body
    assert "long_video_output/result/long-video.mp4" in body
    assert "fail-fast: false" in body
    assert "max-parallel: 1" in body
    assert "youtube-upload" not in body.lower()
