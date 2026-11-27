from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest
import local_voice


def fake_voice(*, native=True, silent=False):
    mapping = {c: [10+i] for i, c in enumerate('abcdefghijklmnopqrstuvwxyz.')}
    mapping.update({'^': [1], '$': [2], '_': [0], ' ': [3]})
    def phonemize(token):
        return [list('one hundred' if token == '100' else token.lower())]
    def audio(ids, **kwargs):
        counts = np.ones(len(ids), dtype=np.int64) * 100
        signal = np.sin(np.arange(int(sum(counts))) * .2).astype(np.float32)
        if silent:
            signal[:] = 0
        return (signal, counts) if native else signal
    return SimpleNamespace(config=SimpleNamespace(sample_rate=22050, phoneme_id_map=mapping),
                           phonemize=phonemize, phoneme_ids_to_audio=audio)


def test_only_audited_free_models_are_available():
    de = local_voice.provenance('de')
    assert set(local_voice.VOICES) == {'en','de'}
    assert de['license']['id'] == 'CC0-1.0'
    assert de['alignment'] == 'native_phoneme_samples'
    assert len(de['model_sha256']) == 64
    assert local_voice.REVISION in de['model_url']
    assert local_voice.provenance('en')['model'] == 'en_US-joe-medium'
    with pytest.raises(RuntimeError, match='only de/en'):
        local_voice.provenance('fr')
    de['license']['id'] = 'changed'
    assert local_voice.provenance('de')['license']['id'] == 'CC0-1.0'


def test_word_boundary_mapping_preserves_expanded_number():
    voice = fake_voice()
    ids, spans = local_voice._token_ids(voice, ['fish', '100'])
    samples = [100] * len(ids)
    times = local_voice._word_samples(samples, ids, spans, len(ids)*100)
    assert len(times) == 2
    assert times[0][1] < times[1][0]
    # One original number caption spans every phoneme in spoken "one hundred".
    assert times[1][1] - times[1][0] > times[0][1] - times[0][0]


@pytest.mark.parametrize('counts,ids,spans,size', [
    ([1], [1, 2], [(0, 1)], 1),
    ([-1, 2], [1, 2], [(0, 1)], 1),
    ([1.5, 2], [1, 2], [(0, 1)], 3),
    ([1, 2], [1, 2], [(0, 1)], 4),
    ([0, 3], [1, 2], [(0, 1)], 3),
])
def test_invalid_or_estimated_native_counts_fail(counts, ids, spans, size):
    with pytest.raises(RuntimeError):
        local_voice._word_samples(counts, ids, spans, size)


def test_unknown_phoneme_is_rejected_instead_of_dropped():
    with pytest.raises(RuntimeError, match='unsupported phoneme'):
        local_voice._token_ids(fake_voice(), ['fish?'])


def test_nonempty_native_speech_has_exact_caption_words(tmp_path, monkeypatch):
    monkeypatch.setattr(local_voice, '_load_voice', lambda lang: fake_voice())
    speech = local_voice.synthesize('Fish 100 swim.', tmp_path, SimpleNamespace(language='de'))
    assert speech.engine == 'piper' and speech.timing == 'aligned'
    assert [w.text for w in speech.words] == ['Fish', '100', 'swim.']
    assert speech.words[-1].end < speech.duration
    assert speech.provenance['audio_samples'] == round(speech.duration * 22050)
    assert speech.audio.stat().st_size > 1000
    assert not (tmp_path / 'voice-piper.wav.part').exists()


@pytest.mark.parametrize('voice,reason', [(fake_voice(native=False), 'native phoneme'),
                                         (fake_voice(silent=True), 'silent audio')])
def test_no_alignment_or_silent_audio_never_returns_success(tmp_path, monkeypatch, voice, reason):
    monkeypatch.setattr(local_voice, '_load_voice', lambda lang: voice)
    with pytest.raises(RuntimeError, match=reason):
        local_voice.synthesize('Fish swim.', tmp_path, SimpleNamespace(language='de'))
    assert not (tmp_path / 'voice-piper.wav').exists()
    assert not (tmp_path / 'voice-piper.wav.part').exists()


def test_corrupted_cached_model_is_not_loaded(tmp_path):
    file = tmp_path / 'model.onnx'
    file.write_bytes(b'bad')
    with patch('local_voice.urllib.request.build_opener') as opener:
        opener.return_value.open.side_effect = OSError('offline')
        with pytest.raises(OSError):
            local_voice._download('https://huggingface.co/test', file, 'f'*64, 3)
    assert not list(tmp_path.glob('*.part'))


def test_sentence_groups_dont_cut_at_arbitrary_24_words():
    tokens=["word"]*29+["end."]+["Next","sentence."]
    assert [len(g) for g in local_voice._sentence_groups(tokens)]==[30,2]

def test_context_uses_sentence_phonemes_and_keeps_native_ranges():
    voice=fake_voice()
    original=voice.phonemize
    voice.phonemize=lambda text: [list("fash swim.")] if text=="fish swim." else original(text)
    ids,spans=local_voice._context_ids(voice,["fish","swim."])
    assert ids!=local_voice._token_ids(voice,["fish","swim."])[0]
    intervals=local_voice._word_samples([100]*len(ids),ids,spans,len(ids)*100)
    assert len(intervals)==2 and intervals[0][1]<intervals[1][0]

def test_context_ambiguous_expansion_is_not_guessed():
    voice=fake_voice()
    original=voice.phonemize
    voice.phonemize=lambda text: [list("fish one hundred swim.")] if text=="fish 100 swim." else original(text)
    ids,spans=local_voice._context_ids(voice,["fish","100","swim."])
    assert len(spans)==3
    voice.phonemize=lambda text: [list("fish hundred swim.")] if text=="fish 100 swim." else original(text)
    with pytest.raises(ValueError,match="ambiguous contextual word grouping"):
        local_voice._context_ids(voice,["fish","100","swim."])

def test_natural_voice_reports_real_alignment_and_single_gain(tmp_path,monkeypatch):
    monkeypatch.setenv("PURFFLE_NATURAL_VOICE","1")
    monkeypatch.setattr(local_voice,"_load_voice",lambda lang:fake_voice())
    speech=local_voice.synthesize("Fish swim. Birds fly.",tmp_path,SimpleNamespace(language="en"))
    assert [w.text for w in speech.words]==["Fish","swim.","Birds","fly."]
    assert speech.provenance["contextual_sentences"]==2
    assert speech.provenance["isolated_pronunciation_fallback_sentences"]==0
    assert speech.provenance["normalization"]=="one_gain_full_narration"
    assert speech.provenance["audio_samples"]==round(speech.duration*22050)
