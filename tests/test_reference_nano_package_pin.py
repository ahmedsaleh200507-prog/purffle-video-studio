"""Offline checks: all live English workflows use Nano-capable pinned source."""
from pathlib import Path

PIN = "chatterbox-tts @ git+https://github.com/resemble-ai/chatterbox.git@ab55923c27757c90cfcc407baa57dc25a7d25217"

def test_every_english_job_uses_nano_capable_fixed_revision():
    root=Path(__file__).resolve().parents[1]/'.github/workflows'
    for name in ('videos.yml','long-batch.yml'):
        body=(root/name).read_text()
        assert 'chatterbox-tts' not in body
        assert 'faster-whisper' not in body
        assert 'secrets.PURFFLE_REFERENCE_OPUS_B64' not in body
        assert 'requirements-dev.txt' in body

def test_active_long_workflow_never_exposes_private_reference_audio():
    root=Path(__file__).resolve().parents[1]/'.github/workflows'
    for name in ('videos.yml','long-batch.yml'):
        body=(root/name).read_text()
        assert 'chatterbox-tts' not in body
        assert 'faster-whisper' not in body
        assert 'secrets.PURFFLE_REFERENCE_OPUS_B64' not in body
        assert 'requirements-dev.txt' in body
