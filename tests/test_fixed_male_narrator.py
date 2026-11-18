"""Production narrator identity contract: ONE stable MALE Piper voice per language.

The uploaded external reference contains no machine-readable voice-model ID.
This tests a close, fully automated CC0 local male narrator, NOT claiming to
clone or exactly match any real/synthetic voice in the uploaded reference.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import local_voice
from studio_runtime import speak_with_free_fallback


def _speech(tmp_path, voice='en_US-joe-medium', engine='piper'):
    audio = tmp_path / 'voice.wav'
    audio.write_bytes(b'valid-bytes')
    return SimpleNamespace(
        engine=engine, voice=voice,
        audio=audio, timing='aligned', duration=3.0,
        words=[SimpleNamespace(start=0.1, end=0.5, text='Hello')],
        provenance=local_voice.provenance('en'),
    )


def test_audited_male_english_voice_is_stable_and_commercially_usable(monkeypatch):
    monkeypatch.setenv('PURFFLE_NARRATOR_LOCK', '1')
    en = local_voice.provenance('en')
    assert en['engine'] == 'piper'
    assert en['model'] == 'en_US-joe-medium'
    assert en['license']['id'] == 'CC0'
    assert 'en/en_US/joe/medium' in en['model_url']
    assert en['model_revision'] == '0ca208afc2a2ee102b1e961e72e0a7e4907be3d0'
    assert en['model_sha256'] == 'abf4b998e34045cbd00eaf050de2de620f81ded6eb8b85a24b022a1c2b3f08d2'
    assert local_voice._voice_key('en') == 'en_male'
    assert local_voice.provenance('en') == en


def test_german_uses_same_existing_audited_male_voice(monkeypatch):
    monkeypatch.setenv('PURFFLE_NARRATOR_LOCK', '1')
    de = local_voice.provenance('de')
    assert de['model'] == 'de_DE-thorsten-medium'
    assert de['license']['id'] == 'CC0-1.0'
    assert local_voice._voice_key('de') == 'de'


def test_existing_legacy_pipeline_still_available_when_not_locked(monkeypatch):
    monkeypatch.delenv('PURFFLE_NARRATOR_LOCK', raising=False)
    assert local_voice.provenance('en')['model'] == 'en_US-ljspeech-high'


def test_locked_narrator_never_attempts_edge_and_records_identity(tmp_path, monkeypatch):
    monkeypatch.setenv('PURFFLE_NARRATOR_LOCK', '1')
    monkeypatch.setenv('VOICE_REPORT', str(tmp_path / 'voice-report.json'))
    expected = _speech(tmp_path)
    called = []

    def forbidden_edge():
        raise AssertionError('Edge voice should not be tried with lock')

    def local():
        called.append('piper')
        return expected

    settings = SimpleNamespace(language='en', offline=False, tts_engine='edge')
    got = speak_with_free_fallback(None, tmp_path, settings, forbidden_edge, local)
    assert got is expected
    assert called == ['piper']
    report = json.loads((tmp_path / 'voice-report.json').read_text())
    assert report['state'] == 'ready'
    assert report['narrator_lock'] is True
    assert report['voice'] == 'en_US-joe-medium'
    assert report['engine'] == 'piper'
    assert [x['engine'] for x in report['attempts']] == ['piper']


def test_locked_narrator_cannot_fall_back_to_previous_female_voice(tmp_path, monkeypatch):
    monkeypatch.setenv('PURFFLE_NARRATOR_LOCK', '1')
    monkeypatch.setenv('VOICE_REPORT', str(tmp_path / 'voice-report.json'))
    rejected = _speech(tmp_path, 'en_US-ljspeech-high')
    settings = SimpleNamespace(language='en', offline=False, tts_engine='edge')
    with pytest.raises(RuntimeError, match='Locked male narrator unavailable'):
        speak_with_free_fallback(None, tmp_path, settings,
                                 lambda: pytest.fail('Edge must not run'),
                                 lambda: rejected)
    report = json.loads((tmp_path / 'voice-report.json').read_text())
    assert report['state'] == 'failed'
    assert [a['engine'] for a in report['attempts']] == ['piper']


def test_locked_narrator_download_failure_is_explicit_not_voice_switch(tmp_path, monkeypatch):
    monkeypatch.setenv('PURFFLE_NARRATOR_LOCK', '1')
    monkeypatch.setenv('VOICE_REPORT', str(tmp_path / 'voice-report.json'))
    settings = SimpleNamespace(language='en', offline=False, tts_engine='edge')
    with pytest.raises(RuntimeError, match='Locked male narrator unavailable'):
        speak_with_free_fallback(
            None, tmp_path, settings, lambda: pytest.fail('Edge forbidden'),
            lambda: (_ for _ in ()).throw(RuntimeError('model download failed')))
    report = json.loads((tmp_path / 'voice-report.json').read_text())
    assert report['state'] == 'failed'
    assert 'model download failed' in report['attempts'][0]['error']


def test_model_config_must_match_audited_joe_file(tmp_path):
    cfg = tmp_path / 'voice.json'
    cfg.write_text(json.dumps({
        'audio': {'sample_rate': 22050},
        'espeak': {'voice': 'en-us'},
        'num_speakers': 1, 'phoneme_type': 'espeak',
        'phoneme_id_map': {'^': [1], '$': [2], '_': [0], ' ': [3]},
        'padding': 'x'*200,
    }))
    local_voice._validate_sidecar(cfg, model='en_US-joe-medium', role='config')
    data = json.loads(cfg.read_text())
    data['num_speakers'] = 2
    cfg.write_text(json.dumps(data))
    with pytest.raises(RuntimeError, match='incompatible'):
        local_voice._validate_sidecar(cfg, model='en_US-joe-medium', role='config')


def test_model_card_requires_cc0_provenance_and_retrained_base(tmp_path):
    card = tmp_path / 'MODEL_CARD'
    card.write_text(
        '# Model card for joe (medium)\n'
        'Language en_US. License: CC0. Finetuned from rdh base model.\n'
        + 'x'*230)
    local_voice._validate_sidecar(card, model='en_US-joe-medium', role='card')
    card.write_text(card.read_text().replace('License: CC0', 'License: CC BY-NC-SA'))
    with pytest.raises(RuntimeError, match='CC0'):
        local_voice._validate_sidecar(card, model='en_US-joe-medium', role='card')


def test_video_workflow_actually_enables_fixed_male_voice():
    path = Path(__file__).resolve().parents[1] / '.github/workflows/videos.yml'
    text = path.read_text()
    assert "PURFFLE_NARRATOR_LOCK: '1'" in text
    assert 'PIPER' not in text.upper() or 'MALE' in text.upper()


def test_mp4_validator_rejects_voice_identity_mismatch_even_with_audio(tmp_path, monkeypatch):
    from render_job import validate_result
    from media_validation import QualityValidator
    monkeypatch.setenv('PURFFLE_NARRATOR_LOCK', '1')
    monkeypatch.setenv('LANGUAGE', 'en')
    movie = tmp_path / 'short.mp4'
    movie.write_bytes(b'fake-mp4')
    subtitles = tmp_path / 'captions.srt'
    subtitles.write_text('1\n00:00:00,000 --> 00:00:03,000\nHello!\n')
    footprint = tmp_path / 'footage-report.json'
    footprint.write_text(json.dumps({'scenes': []}))
    with patch.object(QualityValidator, 'validate',
                      return_value={'width': 720, 'height': 1280,
                                    'has_audio': True, 'duration': 3}):
        with pytest.raises(RuntimeError, match='Narrator identity mismatch'):
            validate_result(movie,
                            {'voice': 'piper:en_US-ljspeech-high',
                             'timing': 'aligned', 'language': 'en'},
                            subtitles, footprint)


def test_mp4_validator_accepts_matching_locked_male_provenance(tmp_path, monkeypatch):
    from render_job import validate_result
    from media_validation import QualityValidator
    monkeypatch.setenv('PURFFLE_NARRATOR_LOCK', '1')
    monkeypatch.setenv('LANGUAGE', 'en')
    movie = tmp_path / 'short.mp4'
    movie.write_bytes(b'fake-mp4')
    subtitles = tmp_path / 'captions.srt'
    subtitles.write_text('1\n00:00:00,000 --> 00:00:03,000\nHello!\n')
    footprint = tmp_path / 'footage-report.json'
    footprint.write_text(json.dumps({'scenes': [{
        'index': 1, 'status': 'selected', 'source': 'pixabay',
        'sha256': 'b'*64, 'match': {'visual_score': 0.44},
        'license': {'id': 'Pixabay'},
        'quality': {'portrait_crop_scale': 1.0},
    }]}))
    proof = tmp_path / 'voice-report.json'
    proof.write_text(json.dumps({
        'state': 'ready', 'engine': 'piper',
        'voice': 'en_US-joe-medium', 'timing': 'aligned',
        'provenance': local_voice.provenance('en'),
    }))
    with patch.object(QualityValidator, 'validate',
                      return_value={'width': 720, 'height': 1280,
                                    'has_audio': True, 'duration': 3}):
        probe, footage = validate_result(
            movie, {'voice': 'piper:en_US-joe-medium',
                    'timing': 'aligned', 'language': 'en'},
            subtitles, footprint, proof)
    assert probe['has_audio'] and len(footage['scenes']) == 1
