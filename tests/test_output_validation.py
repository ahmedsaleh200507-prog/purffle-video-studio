"""Output acceptance requires complete provenance, native/aligned voice and captions."""
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from render_job import validate_result


@pytest.fixture
def output(tmp_path):
    video = tmp_path / 'short.mp4'
    video.write_bytes(b'test fixture; ffprobe mocked')
    captions = tmp_path / 'captions.srt'
    captions.write_text('1\n00:00:00,000 --> 00:00:01,000\nHello\n', encoding='utf-8')
    report = tmp_path / 'footage-report.json'
    report.write_text(json.dumps({'scenes': [{'status': 'selected', 'source': 'test'}]}))
    return video, captions, report


def probe(width=1080, height=1920):
    return {'width': width, 'height': height, 'duration': 1.2, 'has_audio': True}


def test_output_requires_exact_size(output):
    video, captions, report = output
    with patch('media_validation.QualityValidator.validate', return_value=probe(720, 1280)):
        with pytest.raises(RuntimeError, match='1080x1920'):
            validate_result(video, {'voice': 'edge:test', 'timing': 'native'}, captions, report)


def test_output_requires_actual_audio_stream(output):
    video, captions, report = output
    no_audio = probe()
    no_audio.pop('has_audio')
    with patch('media_validation.QualityValidator.validate', return_value=no_audio), \
            patch('subprocess.run', return_value=SimpleNamespace(stdout='{"streams":[{"codec_type":"video"}]}')):
        with pytest.raises(RuntimeError, match='no narration audio'):
            validate_result(video, {'voice': 'edge:test', 'timing': 'native'}, captions, report)


@pytest.mark.parametrize('metadata', [
    {'voice': 'silent:test', 'timing': 'native'},
    {'voice': 'edge:test', 'timing': 'estimated'},
    {'voice': 'edge:test', 'timing': 'anchored'},
])
def test_output_rejects_unverified_narration(output, metadata):
    video, captions, report = output
    with patch('media_validation.QualityValidator.validate', return_value=probe()):
        with pytest.raises(RuntimeError, match='verified native/aligned'):
            validate_result(video, metadata, captions, report)


def test_output_rejects_missing_captions_or_unverified_scenes(output):
    video, captions, report = output
    metadata = {'voice': 'edge:test', 'timing': 'native'}
    with patch('media_validation.QualityValidator.validate', return_value=probe()):
        report.write_text(json.dumps({'scenes': [{'status': 'failed'}]}))
        with pytest.raises(RuntimeError, match='Not every scene'):
            validate_result(video, metadata, captions, report)
        captions.unlink()
        with pytest.raises(RuntimeError, match='captions missing'):
            validate_result(video, metadata, captions, report)


def test_accepts_complete_validated_output(output):
    video, captions, report = output
    with patch('media_validation.QualityValidator.validate', return_value=probe()):
        info, provenance = validate_result(video, {'voice': 'edge:test', 'timing': 'native'}, captions, report)
    assert info['width'] == 1080
    assert provenance['scenes'][0]['status'] == 'selected'


def test_local_voice_requires_pinned_licensed_native_alignment(output, tmp_path):
    from local_voice import provenance
    video, captions, report = output
    meta = {'voice': 'piper:en_US-ljspeech-high', 'timing': 'aligned'}
    voice_report = tmp_path / 'voice-report.json'
    voice_data = {'state': 'ready', 'engine': 'piper', 'voice': 'en_US-ljspeech-high',
                  'timing': 'aligned', 'provenance': provenance('en')}
    with patch('media_validation.QualityValidator.validate', return_value=probe()):
        with pytest.raises(RuntimeError, match='report missing'):
            validate_result(video, meta, captions, report, voice_report)
        voice_report.write_text(json.dumps(voice_data))
        validate_result(video, meta, captions, report, voice_report)
        voice_data['provenance']['model_sha256'] = 'a' * 64
        voice_report.write_text(json.dumps(voice_data))
        with pytest.raises(RuntimeError, match='provenance invalid'):
            validate_result(video, meta, captions, report, voice_report)
