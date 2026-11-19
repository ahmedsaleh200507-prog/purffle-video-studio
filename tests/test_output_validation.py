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
    report.write_text(json.dumps({'scenes': [{
        'index': 1, 'status': 'selected', 'source': 'test',
        'sha256': 'fixture-sha256', 'match': {'visual_score': .35},
        'license': {'id': 'CC0-1.0'},
        'quality': {'width': 1080, 'height': 1920, 'portrait_crop_scale': .66667},
    }]}))
    return video, captions, report


def probe(width=720, height=1280):
    return {'width': width, 'height': height, 'duration': 1.2, 'has_audio': True}


def test_output_requires_exact_size(output):
    video, captions, report = output
    with patch('media_validation.QualityValidator.validate', return_value=probe(1080, 1920)):
        with pytest.raises(RuntimeError, match='Output resolution mismatch'):
            validate_result(video, {'language': 'de', 'voice': 'edge:test', 'timing': 'native'}, captions, report)


def test_output_requires_actual_audio_stream(output):
    video, captions, report = output
    no_audio = probe()
    no_audio.pop('has_audio')
    with patch('media_validation.QualityValidator.validate', return_value=no_audio), \
            patch('subprocess.run', return_value=SimpleNamespace(stdout='{"streams":[{"codec_type":"video"}]}')):
        with pytest.raises(RuntimeError, match='no narration audio'):
            validate_result(video, {'language': 'de', 'voice': 'edge:test', 'timing': 'native'}, captions, report)


@pytest.mark.parametrize('metadata', [
    {'language': 'de', 'voice': 'silent:test', 'timing': 'native'},
    {'language': 'de', 'voice': 'edge:test', 'timing': 'estimated'},
    {'language': 'de', 'voice': 'edge:test', 'timing': 'anchored'},
])
def test_output_rejects_unverified_narration(output, metadata):
    video, captions, report = output
    with patch('media_validation.QualityValidator.validate', return_value=probe()):
        with pytest.raises(RuntimeError, match='verified native/aligned'):
            validate_result(video, metadata, captions, report)


def test_output_rejects_missing_captions_or_unverified_scenes(output):
    video, captions, report = output
    metadata = {'language': 'de', 'voice': 'edge:test', 'timing': 'native'}
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
        info, provenance = validate_result(video, {'language': 'de', 'voice': 'edge:test', 'timing': 'native'}, captions, report)
    assert info['width'] == 720
    assert provenance['scenes'][0]['status'] == 'selected'


def test_local_voice_requires_pinned_licensed_native_alignment(output, tmp_path):
    from local_voice import provenance
    video, captions, report = output
    meta = {'language': 'de', 'voice': 'piper:de_DE-thorsten-medium', 'timing': 'aligned'}
    voice_report = tmp_path / 'voice-report.json'
    voice_data = {'state': 'ready', 'engine': 'piper', 'voice': 'de_DE-thorsten-medium',
                  'timing': 'aligned', 'provenance': provenance('de')}
    with patch('media_validation.QualityValidator.validate', return_value=probe()):
        with pytest.raises(RuntimeError, match='report missing'):
            validate_result(video, meta, captions, report, voice_report)
        voice_report.write_text(json.dumps(voice_data))
        validate_result(video, meta, captions, report, voice_report)
        voice_data['provenance']['model_sha256'] = 'a' * 64
        voice_report.write_text(json.dumps(voice_data))
        with pytest.raises(RuntimeError, match='provenance invalid'):
            validate_result(video, meta, captions, report, voice_report)
