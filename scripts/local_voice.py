"""Free local English/German neural speech with native, measured phoneme word timings.

Only the audited Joe and Thorsten Piper voices may be loaded. Contextual
sentence phonemization is preferred when original caption token boundaries
can be mapped safely. Timing comes from measured model sample counts.
"""
from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
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
# V4: exactly the two user-requested Piper identities; no voice fallback.
VOICES = {
    'en': {
        'model': 'en_US-joe-medium',
        'folder': 'en/en_US/joe/medium',
        'revision': '0ca208afc2a2ee102b1e961e72e0a7e4907be3d0',
        'license': {'id': 'CC0', 'source': 'https://github.com/OHF-Voice/voice-datasets'},
        'files': {
            '.onnx': ('abf4b998e34045cbd00eaf050de2de620f81ded6eb8b85a24b022a1c2b3f08d2', 63221984),
        },
        'verify_text_files': True,
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


def _voice_key(language):
    # Selection is per job, never per sentence. A failed locked male voice
    # must fail visibly, not silently switch to a different/female narrator.
    if language not in ('en', 'de'):
        raise RuntimeError('Local narration supports only de/en')
    return language


def provenance(language):
    key = _voice_key(language)
    if key not in VOICES:
        raise RuntimeError('Local narration supports only de/en')
    voice = VOICES[key]
    revision = voice.get('revision', REVISION)
    base = f'https://huggingface.co/{REPOSITORY}/resolve/{revision}/{voice["folder"]}/'
    return {'engine': 'piper', 'model': voice['model'], 'model_revision': revision,
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


def _validate_sidecar(path, *, model, role):
    body = Path(path).read_bytes()
    if not 200 <= len(body) <= 12000:
        raise RuntimeError('Pinned Piper voice sidecar has an invalid size')
    if role == 'card':
        text = body.decode('utf-8')
        if ('License: CC0' not in text or 'rdh' not in text
                or 'joe' not in text.lower()):
            raise RuntimeError('Pinned male Piper model card lacks expected CC0 provenance')
        return
    data = json.loads(body)
    required = ('^', chr(36), '_', ' ')
    if (data.get('audio', {}).get('sample_rate') != 22050
            or data.get('espeak', {}).get('voice') != 'en-us'
            or data.get('num_speakers') != 1
            or data.get('phoneme_type') != 'espeak'
            or not isinstance(data.get('phoneme_id_map'), dict)
            or not all(k in data['phoneme_id_map'] for k in required)):
        raise RuntimeError('Pinned male Piper config is incompatible or invalid')


def _download_verified_sidecar(url, target, *, model, role):
    target = Path(target)
    if target.exists():
        try:
            _validate_sidecar(target, model=model, role=role)
            return target
        except (ValueError, UnicodeError, RuntimeError):
            target.unlink(missing_ok=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    opener = urllib.request.build_opener(_ModelRedirects())
    request = urllib.request.Request(
        url, headers={'User-Agent': 'PurffleVideoStudio/3.0 pinned male model'})
    with opener.open(request, timeout=25) as response:
        body = response.read(12001)
    if len(body) > 12000:
        raise RuntimeError('Pinned Piper voice sidecar exceeds audited size')
    fd, name = tempfile.mkstemp(dir=target.parent, suffix='.sidecar.part')
    path = Path(name)
    try:
        with os.fdopen(fd, 'wb') as output:
            output.write(body)
        _validate_sidecar(path, model=model, role=role)
        path.replace(target)
        return target
    finally:
        path.unlink(missing_ok=True)


def _voice_files(language):
    info = provenance(language)
    voice = VOICES[_voice_key(language)]
    root = (Path(os.environ.get('PURFFLE_PIPER_CACHE', '.cache/piper'))
            / info['model_revision'])
    root.mkdir(parents=True, exist_ok=True)
    base = info['model_url'].rsplit('/', 1)[0] + '/'
    for suffix, (digest, size) in voice['files'].items():
        name = 'MODEL_CARD' if suffix == 'MODEL_CARD' else voice['model'] + suffix
        target = root / (voice['model'] + '-MODEL_CARD' if suffix == 'MODEL_CARD' else name)
        _download(base + name, target, digest, size)
    if voice.get('verify_text_files'):
        config = root / (voice['model'] + '.onnx.json')
        card = root / (voice['model'] + '-MODEL_CARD')
        _download_verified_sidecar(base + voice['model'] + '.onnx.json', config,
                                   model=voice['model'], role='config')
        _download_verified_sidecar(base + 'MODEL_CARD', card,
                                   model=voice['model'], role='card')
    return root / (voice['model'] + '.onnx')


@lru_cache(maxsize=2)
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


VOICE_FLOW_VERSION="sentence_context_v1"

def flow_enabled():
    return os.getenv("PURFFLE_NATURAL_VOICE")=="1"

def _sentence_groups(tokens,limit=60):
    """Keep sentence boundaries; split an exceptionally long sentence at a clause."""
    pending=[]
    for token in tokens:
        pending.append(token)
        if token.rstrip("\"”’')]").endswith((".", "!", "?")):
            yield pending
            pending=[]
        elif len(pending)>=limit:
            cuts=[i+1 for i,t in enumerate(pending) if i>=limit//2 and t.endswith((",", ";", ":"))]
            cut=cuts[-1] if cuts else limit
            yield pending[:cut]
            pending=pending[cut:]
    if pending:
        yield pending

def _phoneme_words(phonemes):
    groups=[]
    for p in phonemes:
        if p==" ":
            if groups and groups[-1]:
                groups.append([])
        else:
            if not groups:
                groups.append([])
            groups[-1].append(p)
    return [g for g in groups if g]

def _context_ids(voice,tokens):
    """Use eSpeak's actual sentence pronunciation, not concatenated word pronunciations.

    Map contextual word groups only when the count and per-token local
    pronunciation are consistent. Never guess timing for ambiguous expansions.
    """
    from difflib import SequenceMatcher
    sentences=voice.phonemize(" ".join(tokens))
    if len(sentences)!=1:
        raise ValueError("ambiguous contextual sentence segmentation")
    phonemes=list(sentences[0])
    groups=_phoneme_words(phonemes)
    expected=[_phoneme_words([p for s in voice.phonemize(t) for p in s]) for t in tokens]
    if any(not g for g in expected) or sum(map(len,expected))!=len(groups):
        raise ValueError("ambiguous contextual word grouping")
    # Preserve original phoneme sequence including spaces and punctuation.
    # Group indices refer to real phoneme positions, not estimated time.
    positions=[]
    start=None
    for i,p in enumerate(phonemes+[" "]):
        if p!=" " and start is None:
            start=i
        elif p==" " and start is not None:
            positions.append((start,i))
            start=None
    mapping=voice.config.phoneme_id_map
    ids=list(mapping["^"])+list(mapping["_"])
    bounds=[len(ids)]
    for p in phonemes:
        if p not in mapping or not mapping[p]:
            raise ValueError("context phoneme unavailable")
        ids.extend(mapping[p]); ids.extend(mapping["_"])
        bounds.append(len(ids))
    spans=[]
    cursor=0
    for local in expected:
        n=len(local)
        actual=groups[cursor:cursor+n]
        a=[p for g in local for p in g if p not in ("ˈ","ˌ")]
        b=[p for g in actual for p in g if p not in ("ˈ","ˌ")]
        # Allow ordinary contextual pronunciation variation; abstain on
        # unrelated sequences or uncertain token grouping.
        if a!=b and SequenceMatcher(None,a,b,autojunk=False).ratio()<.60:
            raise ValueError("ambiguous contextual token alignment")
        spans.append((bounds[positions[cursor][0]],bounds[positions[cursor+n-1][1]]))
        cursor+=n
    ids.extend(mapping["$"])
    if len(ids)>8000:
        raise ValueError("context phoneme budget exceeded")
    return ids,spans

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
    flow=flow_enabled()
    chunks=list(_sentence_groups(tokens)) if flow else [tokens[i:i+24] for i in range(0,len(tokens),24)]
    contextual,fallback=0,0
    signals=[]
    try:
        with wave.open(str(temp), 'wb') as wav:
            wav.setparams((1, 2, sample_rate, 0, 'NONE', 'not compressed'))
            # Bound individual ONNX inference allocations while keeping natural
            # phrase punctuation and a single native timeline for the whole WAV.
            for chunk_tokens in chunks:
                if flow:
                    try:
                        ids,spans=_context_ids(voice,chunk_tokens)
                        contextual+=1
                    except ValueError:
                        ids,spans=_token_ids(voice,chunk_tokens)
                        fallback+=1
                else:
                    ids,spans=_token_ids(voice,chunk_tokens)
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
                if flow:
                    signals.append(audio)
                else:
                    audio = np.clip(audio / peak * .95, -1, 1)
                    wav.writeframes((audio * 32767).astype(np.int16).tobytes())
                words.extend(Word(token, (total_samples+a)/sample_rate, (total_samples+b)/sample_rate)
                             for token, (a, b) in zip(chunk_tokens, timings))
                total_samples += len(audio)
                if total_samples / sample_rate > 180:
                    raise RuntimeError('Local narration duration budget exceeded')
            if flow:
                # A single gain across the narration avoids sentence-wise
                # peak normalization jumps; never change sample timings.
                gain=.95/max(float(np.max(np.abs(a))) for a in signals)
                for audio in signals:
                    wav.writeframes((np.clip(audio*gain,-1,1)*32767).astype(np.int16).tobytes())
        if len(words) != len(tokens):
            raise RuntimeError('Caption tokens were lost during native alignment')
        temp.replace(target)
    finally:
        temp.unlink(missing_ok=True)
    info.update(sample_rate=sample_rate, audio_samples=total_samples, word_count=len(words),
                timing='aligned', timing_source='native_phoneme_samples')
    if flow:
        info.update(method='Sentence-context phonemization with explicit original-token mapping and native sample counts',
                    voice_flow_version=VOICE_FLOW_VERSION,contextual_sentences=contextual,
                    isolated_pronunciation_fallback_sentences=fallback,sentence_chunks=len(chunks),
                    normalization='one_gain_full_narration')
        print(f'[VOICE FLOW] contextual={contextual} fallback={fallback} chunks={len(chunks)}',flush=True)
    speech = Speech(target, words, total_samples/sample_rate, 'piper', info['model'], 'aligned')
    speech.provenance = info
    print(f"[VOICE] engine=piper model={info['model']} native_words={len(words)} duration={speech.duration:.3f}", flush=True)
    return speech
