"""Offline checks: all live English workflows use Nano-capable pinned source."""
from pathlib import Path

PIN = "chatterbox-tts @ git+https://github.com/resemble-ai/chatterbox.git@ab55923c27757c90cfcc407baa57dc25a7d25217"

def test_every_english_job_uses_nano_capable_fixed_revision():
    root=Path(__file__).resolve().parents[1] / ".github" / "workflows"
    for name in ("videos.yml", "daily-life-five-20261118.yml",
                 "one-german-bathroom-mirror-20261118.yml",
                 "one-video-volcanic-island-20261118.yml"):
        y=(root/name).read_text()
        assert PIN in y
        assert "chatterbox-tts==0.1.7" not in y
        assert "secrets.PURFFLE_REFERENCE_OPUS_B64" in y

def test_smoke_never_exposes_reference_audio_or_secret():
    path=(Path(__file__).resolve().parents[1] / ".github" /
          "workflows" / "reference-voice-live-smoke-20261119.yml")
    y=path.read_text()
    assert "python scripts/english_reference_policy.py" in y
    assert "python scripts/reference_voice_smoke.py" in y
    assert "secrets.PURFFLE_REFERENCE_OPUS_B64" in y
    assert "actions/upload-artifact@" not in y
    assert "on:\n  push:" in y
