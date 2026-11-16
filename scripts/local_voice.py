"""Free local DE/EN neural speech with native, measured phoneme word timings.

Only the two audited public-domain/CC0 Piper voices below may be loaded. Tokens
are phonemized individually, then synthesized together, so original caption
words (including expanded numbers) retain exact phoneme-ID ranges. Timing comes
from the model's native sample counts; unsupported alignment fails explicitly.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
import time
import urllib.parse
import urllib.request
import wave

REVISION = 'e9ab671f2a0e50a701b34361136ba3e6a3a9eb0c'
REPOSITORY = 'rhasspy/piper-voices'
VOICES = {
    'en': {
        'model': 'en_US-ljspeech-high', 'folder': 'en/en_US/ljspeech/high',
        'license': {'id': 'Public-Domain', 'source': 'https://keithito.com/LJ-Speech-Dataset/'},
        'files': {
            '.onnx': ('5d4f08ba6a2a48c44592eed3ce56bf85e9de3dd4e20df90541ae68a8310c029a', 114199011),
            '.onnx.json': ('7e1f4634af596d83cca997fb7a931ba80b70f8a316a2655ee69c55365e0ace14', 4970),
            'MODEL_CARD': ('289f7421072d689a3d91f6c632f486af46f9b8b04417536104a4ea667b8a394b', 513),
        },
    },
    'de': {
        'model': 'de_DE-thorsten-medium', 'folder': 'de/de_DE/thorsten/medium',
        'license': {'id': 'CC0-1.0', 'source': 'https://github.com/thorstenMueller/Thorsten-Voice'},
        'files': {
            '.onnx': ('fd270eb3d1ebf91d763f8a0f949b1b1bebdfefaea18c3aaf8577dd34536e064f', 63221984),
            '.onnx.json': ('cf245c91668e74cb6716f38647ae3d6d9bac42965872596f65f9ab2b7d7221ed', 5460),
            'MODEL_CARD': ('c638118fb06eb07d59e60270097c250cf2de81a037320a8a6306fec652ad13b0', 427),
        },
    },
}


def provenance(language):
    if language not in VOICES:
        raise RuntimeError('Local narration supports only de/en')
    voice = VOICES[language]
    base = f'https://huggingface.co/{REPOSITORY}/resolve/{REVISION}/{voice["folder"]}/'
    return {'engine': 'piper', 'model': voice['model'], 'model_revision': REVISION,
            'model_url': base + voice['model'] + '.onnx',
            'model_sha256': voice['files']['.onnx'][0],
            'license': {**deepcopy(voice['license']), 'url': base + 'MODEL_CARD'},
            'alignment': 'native_phoneme_samples', 'software_license': 'GPL-3.0-or-later',
            'software_source': 'https://github.com/OHF-Voice/piper1-gpl',
            'model_repository_license': 'MIT',
            'model_repository_license_url': f'https://huggingface.co/{REPOSITORY}/blob/{REVISION}/README.md',
            'method': 'Original tokens phonemized separately, synthesized together; native phoneme-ID sample spans'}


def _hash(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(part)
    return digest.hexdigest()


class _ModelRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        host = urllib.parse.urlsplit(newurl).hostname or ''
        if urllib.parse.urlsplit(newurl).scheme != 'https' or not (
                host == 'huggingface.co' or host.endswith('.huggingface.co')
                or host.endswith('.hf.co') or host.endswith('.xethub.hf.co')):
            raise RuntimeError('Unexpected local voice model download redirect')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _download(url, target, expected_hash, expected_bytes):
    target = Path(target)
    if target.is_file() and target.stat().st_size == expected_bytes and _hash(target) == expected_hash:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    fd, name = tempfile.mkstemp(dir=target.parent, suffix='.part')
    temp = Path(name)
    try:
        request = urllib.request.Request(url, headers={'User-Agent': 'PurffleVideoStudio/2.0 model fetch'})
        opener = urllib.request.build_opener(_ModelRedirects())
        with os.fdopen(fd, 'wb') as output, opener.open(request, timeout=25) as response:
            count = 0
            while True:
                if time.monotonic() - started > 120:
                    raise RuntimeError('Local voice model download exceeded 120s')
                part = response.read(min(65536, expected_bytes - count + 1))
                if not part:
                    break
                count += len(part)
                if count > expected_bytes:
                    raise RuntimeError('Local voice model exceeds audited size')
                output.write(part)
        if count != expected_bytes or _hash(temp) != expected_hash:
            raise RuntimeError('Local voice artifact does not match audited SHA256/size')
        temp.replace(target)
        return target
    finally:
        temp.unlink(missing_ok=True)


def _voice_files(language):
    info = provenance(language)
    voice = VOICES[language]
    root = Path(os.environ.get('PURFFLE_PIPER_CACHE', '.cache/piper')) / REVISION
    root.mkdir(parents=True, exist_ok=True)
    base = info['model_url'].rsplit('/', 1)[0] + '/'
    for suffix, (digest, size) in voice['files'].items():
        name = 'MODEL_CARD' if suffix == 'MODEL_CARD' else voice['model'] + suffix
        target = root / (voice['model'] + '-MODEL_CARD' if suffix == 'MODEL_CARD' else name)
        _download(base + name, target, digest, size)
    return root / (voice['model'] + '.onnx')


def _load_voice(language):
    import onnx
    import onnxruntime
    from piper import PiperVoice
    from piper.config import PiperConfig
    from piper.patch_voice_with_alignment import add_alignment_output
    path = _voice_files(language)
    model = onnx.load(str(path), load_external_data=False)
    add_alignment_output(model)
    options = onnxruntime.SessionOptions()
    options.intra_op_num_threads = 2
    options.inter_op_num_threads = 1
    options.enable_mem_pattern = False
    session = onnxruntime.InferenceSession(model.SerializeToString(), sess_options=options,
                                           providers=['CPUExecutionProvider'])
    return PiperVoice(session=session, config=PiperConfig.from_dict(json.loads(path.with_suffix('.onnx.json').read_text())))


def _token_ids(voice, tokens):
    """Return explicit token ID ranges; unknown phonemes are never discarded."""
    mapping = voice.config.phoneme_id_map
    pad = mapping['_']
    ids = list(mapping['^']) + list(pad)
    spans = []
    for index, token in enumerate(tokens):
        if index:
            if ' ' not in mapping:
                raise RuntimeError('Voice has no word boundary phoneme')
            ids.extend(mapping[' ']); ids.extend(pad)
        begin = len(ids)
        phonemes = [p for sentence in voice.phonemize(token) for p in sentence]
        if not phonemes:
            raise RuntimeError(f'Local voice could not phonemize caption token {token!r}')
        for phoneme in phonemes:
            if phoneme not in mapping or not mapping[phoneme]:
                raise RuntimeError('Local voice encountered an unsupported phoneme')
            ids.extend(mapping[phoneme]); ids.extend(pad)
        spans.append((begin, len(ids)))
    ids.extend(mapping['$'])
    if len(ids) > 8000:
        raise RuntimeError('Local voice phoneme budget exceeded')
    return ids, spans


def _word_samples(samples, ids, spans, audio_samples):
    """Validate and sum actual model sample counts, with no timing estimates."""
    counts = [int(value) for value in samples]
    if len(counts) != len(ids) or any(value < 0 for value in counts):
        raise RuntimeError('Native phoneme alignment is incomplete')
    if any(float(original) != count for original, count in zip(samples, counts)):
        raise RuntimeError('Native phoneme sample counts are not integral')
    if sum(counts) != audio_samples:
        raise RuntimeError('Native phoneme sample counts do not cover the actual audio')
    cumulative = [0]
    for count in counts:
        cumulative.append(cumulative[-1] + count)
    words = [(cumulative[a], cumulative[b]) for a, b in spans]
    if any(a >= b for a, b in words) or any(a[1] > b[0] for a, b in zip(words, words[1:])):
        raise RuntimeError('Native caption word intervals are invalid')
    return words


def synthesize(text, out, settings):
    """Produce an upstream Speech; failures never return silent/estimated audio."""
    import numpy as np
    from purffle_shorts.timing import Word, tokenize
    from purffle_shorts.tts import Speech
    language = settings.language
    info = provenance(language)
    tokens = tokenize(text, language)
    if not tokens or len(tokens) > 400 or len(text) > 6000:
        raise RuntimeError('Local narration requires 1–400 words and at most6000characters')
    voice = _load_voice(language)
    sample_rate = int(voice.config.sample_rate)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    target = out / 'voice-piper.wav'
    temp = out / 'voice-piper.wav.part'
    words, total_samples = [], 0
    try:
        with wave.open(str(temp), 'wb') as wav:
            wav.setparams((1, 2, sample_rate, 0, 'NONE', 'not compressed'))
            # Bound individual ONNX inference allocations while keeping natural
            # phrase punctuation and a single native timeline for the whole WAV.
            for begin in range(0, len(tokens), 24):
                chunk_tokens = tokens[begin:begin+24]
                ids, spans = _token_ids(voice, chunk_tokens)
                result = voice.phoneme_ids_to_audio(ids, include_alignments=True)
                if not isinstance(result, tuple) or len(result) != 2 or result[1] is None:
                    raise RuntimeError('Voice model did not provide native phoneme alignments')
                audio, native_samples = result
                audio = np.asarray(audio).reshape(-1)
                if not len(audio) or not np.isfinite(audio).all():
                    raise RuntimeError('Local voice produced invalid audio')
                timings = _word_samples(native_samples, ids, spans, len(audio))
                peak = float(np.max(np.abs(audio)))
                if not math.isfinite(peak) or peak < 1e-5 or float(np.sqrt(np.mean(audio*audio))) < 1e-5:
                    raise RuntimeError('Local voice returned silent audio')
                audio = np.clip(audio / peak * .95, -1, 1)
                wav.writeframes((audio * 32767).astype(np.int16).tobytes())
                words.extend(Word(token, (total_samples+a)/sample_rate, (total_samples+b)/sample_rate)
                             for token, (a, b) in zip(chunk_tokens, timings))
                total_samples += len(audio)
                if total_samples / sample_rate > 180:
                    raise RuntimeError('Local narration duration budget exceeded')
        if len(words) != len(tokens):
            raise RuntimeError('Caption tokens were lost during native alignment')
        temp.replace(target)
    finally:
        temp.unlink(missing_ok=True)
    info.update(sample_rate=sample_rate, audio_samples=total_samples, word_count=len(words),
                timing='aligned', timing_source='native_phoneme_samples')
    speech = Speech(target, words, total_samples/sample_rate, 'piper', info['model'], 'aligned')
    speech.provenance = info
    print(f"[VOICE] engine=piper model={info['model']} native_words={len(words)} duration={speech.duration:.3f}", flush=True)
    return speech
