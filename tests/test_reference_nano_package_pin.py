"""Offline checks: all live English workflows use Nano-capable pinned source."""
from pathlib import Path

PIN = "chatterbox-tts @ git+https://github.com/resemble-ai/chatterbox.git@ab55923c27757c90cfcc407baa57dc25a7d25217"

def test_every_english_job_uses_nano_capable_fixed_revision():
    root=Path(__file__).resolve().parents[1] / ".github" / "workflows"
    for name in ("videos.yml", "long-batch.yml"):
        y=(root/name).read_text()
        assert PIN in y
        assert "chatterbox-tts==0.1.7" not in y
        assert "secrets.PURFFLE_REFERENCE_OPUS_B64" in y

def test_active_long_workflow_never_exposes_private_reference_audio():
    root=Path(__file__).resolve().parents[1] / ".github" / "workflows"
    y=(root/"long-batch.yml").read_text()
    assert "scripts/english_reference_policy.py" in y
    assert "secrets.PURFFLE_REFERENCE_OPUS_B64" in y
    assert "steps.selected.outputs.language == 'en'" in y
    assert "voice-reference.wav" not in y
    assert "long_video_output/result/long-video.mp4" in y
    assert "long_video_output/result/report.json" in y
    assert "actions/upload-artifact@" in y
