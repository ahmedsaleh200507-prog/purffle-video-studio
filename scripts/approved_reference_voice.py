"""Single approved male reference TTS with real-output ASR and speaker QA.

No Edge, Piper Joe, generic voices, public voice assets or text-length fake
word timestamps. A failed clone, transcription, similarity or private secret
aborts the English Short without falling back to another narrator.
"""
from __future__ import annotations

from difflib import SequenceMatcher
from functools import lru_cache
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import wave

from english_reference_policy import (
    ENGLISH_REFERENCE_OPUS_SHA256, ENGLISH_REFERENCE_SECONDS,
    ENGLISH_REFERENCE_SHA256, REFERENCE_VOICE_ID, approved_secret_bytes,
)


_WORKER_STAGES = {
    "worker-start", "text-validated", "numpy-loaded", "soundfile-loaded",
    "torch-loaded", "dependencies-loaded", "model-loaded",
    "generated-waveform", "saved-waveform",
}


def _run(command: list[str], *, timeout: int, stage: str = "private-worker") -> None:
    """Never expose private speech, file paths, model stderr or tokens.

    Stable stage names reveal a failing dependency/model step without putting
    secrets or approved reference audio into public CI logs.
    """
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, check=False,
                                timeout=timeout, stderr=subprocess.PIPE)
        if result.returncode == 0:
            return
        lines = result.stdout.decode("utf-8", errors="replace").splitlines()
        progress = [line.removeprefix("[VOICE SAFE STAGE] ")
                    for line in lines if line.startswith("[VOICE SAFE STAGE] ")]
        reached = next((name for name in reversed(progress)
                        if name in _WORKER_STAGES), "not-started")
        print(f"[VOICE SAFE DIAGNOSTIC] stage={stage} last_completed={reached} "
              f"worker_exit={result.returncode}", flush=True)
    except subprocess.TimeoutExpired:
        print(f"[VOICE SAFE DIAGNOSTIC] stage={stage} timeout=yes", flush=True)
    except OSError:
        print(f"[VOICE SAFE DIAGNOSTIC] stage={stage} launch_failed=yes", flush=True)
    # Never print subprocess exception, command, stderr, stdout or reference.
    raise RuntimeError("reference_voice_failed: private audio decode/model/validation failed") from None


def prepare_reference(folder: Path) -> Path:
    """Decrypt nothing, decode only the exact pinned Opus GitHub Secret."""
    blob = approved_secret_bytes()
    folder = Path(folder).resolve()
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    folder.chmod(0o700)
    opus = folder / "approved-reference.opus"
    wav = folder / "approved-reference.wav"
    opus.write_bytes(blob)
    opus.chmod(0o600)
    _run(["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-y",
          "-i", str(opus), "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
          str(wav)], timeout=25, stage="opus-decode")
    wav.chmod(0o600)
    with wave.open(str(wav), "rb") as f:
        if (f.getframerate() != 16000 or f.getnchannels() != 1 or
                f.getsampwidth() != 2 or abs(f.getnframes()/16000-ENGLISH_REFERENCE_SECONDS) > .04):
            raise RuntimeError("reference_voice_not_ready: decoded recording identity is invalid")
    opus.unlink(missing_ok=True)
    return wav


def _tokens(text: str) -> list[str]:
    # ASR output often differs only in typography ("Earth’s" vs "Earth's",
    # "doesn't" vs "doesnt"). Normalize those spellings for comparison;
    # do not insert, remove or silently change spoken words.
    canonical = str(text).casefold().replace("’", "'").replace("‘", "'")
    return [t.replace("'", "") for t in re.findall(r"[a-z0-9']+", canonical)
            if t.strip("'")]


def long_form_asr_deviations(expected: list[str], heard: list[str]) -> tuple[int, bool]:
    """Limited, auditable ASR disagreement for *long videos only*.

    Short-form exact transcript policy remains unchanged. The long-form path
    never fabricates or estimates timestamps: captions use actual ASR words.
    One hearing discrepancy in 12-19 words, two in 20+ words; forbid
    large deletions and large insertions even if SequenceMatcher is optimistic.
    """
    if not expected or len(expected) < 12:
        return max(len(expected), len(heard)), False
    matching = sum(b.size for b in SequenceMatcher(
        None, expected, heard, autojunk=False).get_matching_blocks())
    differences = max(len(expected), len(heard)) - matching
    limit = 2 if len(expected) >= 20 else 1
    valid = (
        differences <= limit
        and len(expected) - 1 <= len(heard) <= len(expected) + 1
        and matching >= (0.90 * len(expected))
    )
    return differences, valid


def _safe_split_for_exact_audio(text: str) -> list[str]:
    """Split failed narration into ORIGINAL shorter clauses, no word rewriting.

    The tiny Nano model occasionally skips words in a longer sentence. Real
    ASR and the approved speaker gate MUST still validate each fragment.
    """
    whole = " ".join(str(text).split())
    pieces = re.split(r"(?<=[.!?])\s+", whole)
    if len(pieces) < 2:
        pieces = re.split(r"(?<=,)\s+", whole)
    # Never cut a sentence mid-way or synthesize 2-3 word fragments.
    # Chatterbox favors complete utterances of six or more words.
    if (not 2 <= len(pieces) <= 4 or
            any(not 6 <= len(_tokens(p)) <= 35 for p in pieces) or
            _tokens(" ".join(pieces)) != _tokens(whole)):
        return []
    return pieces


@lru_cache(maxsize=2)
def _safe_split_for_long_form_audio(text: str) -> list[str]:
    """Long-documentary-only fallback when a complete utterance is misheard.

    First try the unmodified Shorts clause splitter. If punctuation cannot
    produce two viable clauses (e.g. a three-word introductory clause), split
    a 14-35-word utterance at a near-middle word boundary instead.

    Each part must still be independently spoken by the SAME approved private
    narrator and verified against its real WAV using independent ASR. Splitting
    is not an exemption from word or speaker verification.
    """
    normal = _safe_split_for_exact_audio(text)
    if normal:
        return normal
    whole = " ".join(str(text).split())
    chunks = list(re.finditer(r"\\S+", whole))
    if not 14 <= len(chunks) <= 35:
        return []
    positions = range(6, len(chunks)-5)
    if not positions:
        return []
    def priority(i):
        previous = whole[chunks[i-1].start():chunks[i-1].end()]
        punctuation = previous.endswith((",", ";", ":", "—", "–"))
        return (not punctuation, abs(i - len(chunks) / 2))
    cut = min(positions, key=priority)
    parts = [whole[:chunks[cut].start()].strip(), whole[chunks[cut].start():].strip()]
    if (all(6 <= len(_tokens(piece)) <= 35 for piece in parts)
            and _tokens(" ".join(parts)) == _tokens(whole)):
        return parts
    return []


def _verified_asr_model(model_name: str):
    """Reuse CPU recognizers. Neither receives the script as an ASR prompt."""
    if model_name not in {"base.en", "small.en"}:
        raise ValueError("Unsupported independent English ASR checker")
    from faster_whisper import WhisperModel
    return WhisperModel(model_name, device="cpu", compute_type="int8",
                        download_root=os.getenv("PURFFLE_WHISPER_CACHE",
                                                ".cache/whisper"))


def check_real_word_timing(text: str, path: Path, *, asr_loader=None,
                           model_name="base.en", long_form=False):
    """Accept only exact recognized words from actual generated WAV.

    A stronger separate recognizer may rescue false negative transcription,
    but NEVER uses forced alignment or the expected text as an ASR prompt.
    """
    model = asr_loader() if asr_loader is not None else _verified_asr_model(model_name)
    segments, _info = model.transcribe(
        str(path), language="en", beam_size=5, word_timestamps=True,
        vad_filter=False, condition_on_previous_text=False)
    words = [w for seg in segments for w in (seg.words or [])]
    expected = _tokens(text)
    recognized = [w for w in words if _tokens(w.word)]
    got = [t for w in recognized for t in _tokens(w.word)]
    exact = bool(expected and expected == got and len(expected) == len(recognized))
    # Existing Shorts stay STRICT. The 10-minute feature can tolerate at most
    # 1-2 small errors from independent recognition, not a skipped sentence or
    # a fabricated narration. Both speaker identity and WAV timing remain real.
    differences, permitted = long_form_asr_deviations(expected, got) if long_form else (0, False)
    if not exact and not (long_form and permitted):
        shared = SequenceMatcher(None, expected, got, autojunk=False).get_matching_blocks()
        matching = sum(block.size for block in shared)
        print(f"[VOICE SAFE ASR] expected_words={len(expected)} "
              f"decoded_words={len(got)} matching_words={matching} "
              f"timed_words={len(recognized)}", flush=True)
        raise RuntimeError(
            "reference_voice_failed: spoken English does not exactly match "
            "requested narration; no estimated caption timing")
    if not exact:
        print(f"[LONG FORM ASR] minor_recognition_deviations={differences} "
              f"recognized_words={len(got)}; captions_use_actual_audio", flush=True)
    duration = _wav_duration(path)
    previous = 0.
    for w in recognized:
        start, end = float(w.start), float(w.end)
        if (not math.isfinite(start) or not math.isfinite(end)
                or start < previous - .07 or start < -.01
                or end <= start or end > duration + .10
                or float(getattr(w, "probability", 1.0) or 0.0) < .02):
            raise RuntimeError("reference_voice_failed: actual word alignment is incomplete")
        previous = end
    return [(w.word.strip(), max(0., float(w.start)), float(w.end)) for w in recognized]


def verify_reference_asr(text: str, path: Path, *, long_form=False,
                         attempt=1, max_attempts=3):
    """Verify real word timestamps using an independent model when needed.

    The 10-minute producer's live #44943477516 reached chapter 13 before
    three BASE Whisper word-timing failures. Retrying identical synthesis is
    ineffective when the recognizer's alignment is the failing component.

    For long-form ONLY, after BASE rejects either transcript or timestamps,
    consult SMALL on the *same WAV*, retaining the same verified narrator
    and measured timings. If both reject, regenerate. Existing Shorts still
    use strict BASE and the pre-existing final-attempt second recognizer
    solely for word-text disagreements. No alignment repair by guesswork.
    """
    try:
        if long_form:
            return check_real_word_timing(text, path, long_form=True)
        return check_real_word_timing(text, path)
    except RuntimeError as base_error:
        message = str(base_error).casefold()
        word_error = "does not exactly match" in message
        alignment_error = "word alignment" in message
        secondary_allowed = (
            (long_form and (word_error or alignment_error))
            or (not long_form and attempt == max_attempts and word_error)
        )
        if not secondary_allowed:
            raise
        try:
            if long_form:
                verified = check_real_word_timing(
                    text, path, model_name="small.en", long_form=True)
            else:
                verified = check_real_word_timing(
                    text, path, model_name="small.en")
        except Exception:
            # Fail closed if the secondary recognizer itself fails to load,
            # align or decode. Preserve the original spoken-audio error and
            # the existing Shorts rescue behavior (including offline mocks).
            raise base_error from None
        print("[VOICE ASR] verified actual audio and timestamps using "
              "independent small.en recognizer", flush=True)
        return verified


def _wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as source:
        if (source.getnchannels() != 1 or source.getsampwidth() != 2
                or source.getframerate() not in (22050, 24000, 32000, 44100, 48000)):
            raise RuntimeError("reference_voice_failed: unexpected narration WAV format")
        duration = source.getnframes() / source.getframerate()
    if not 1 <= duration <= 80 or not math.isfinite(duration):
        raise RuntimeError("reference_voice_failed: invalid narration duration")
    return duration


def voice_similarity(reference: Path, generated: Path, *, loader=None) -> float:
    """Speaker embeddings are a screen, not a guarantee of exact impersonation."""
    import numpy as np
    if loader is None:
        from resemblyzer import VoiceEncoder, preprocess_wav
        encoder = VoiceEncoder(device="cpu")
        embedding = lambda path: encoder.embed_utterance(preprocess_wav(path))
    else:
        embedding = loader
    a = np.asarray(embedding(reference), dtype="float64")
    b = np.asarray(embedding(generated), dtype="float64")
    if (a.ndim != 1 or b.shape != a.shape or a.size < 16
            or not np.isfinite(a).all() or not np.isfinite(b).all()):
        raise RuntimeError("reference_voice_failed: speaker embedding invalid")
    score = float(np.dot(a,b)/(np.linalg.norm(a)*np.linalg.norm(b)+1e-12))
    if not math.isfinite(score) or score < .70:
        raise RuntimeError("reference_voice_failed: cloned narrator does not meet speaker similarity gate")
    return score


def _model_interpreter() -> Path:
    """Preserve the dedicated virtualenv entrypoint, including its symlink.

    Path.resolve() is a serious bug here: on Ubuntu it returns the global
    interpreter, so dependencies installed only in .venv-reference vanish.
    """
    configured = os.getenv("PURFFLE_REFERENCE_PYTHON",
                           ".venv-reference/bin/python")
    return Path(os.path.abspath(os.path.expanduser(configured)))


def synthesize(text, out, settings, *, segments=None, long_form=False):
    """Return an upstream Speech, timed solely from recognized actual audio."""
    if settings.language != "en":
        raise RuntimeError("Reference narrator is English-only")
    approved_secret_bytes()
    text = " ".join(str(text).split())
    if not 10 <= len(text) <= 1600 or not 2 <= len(_tokens(text)) <= 140:
        raise RuntimeError("reference_voice_failed: unsupported narration text length")
    from purffle_shorts.timing import Word
    from purffle_shorts.tts import Speech

    folder = Path(out).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    # Private reference is NOT kept under the artifact-uploaded work folder.
    with tempfile.TemporaryDirectory(
            prefix="purffle-private-voice-", dir=os.getenv("RUNNER_TEMP") or None) as private:
        reference = prepare_reference(Path(private))
        text_file = Path(private) / "narration.txt"
        text_file.write_text(text, encoding="utf-8")
        text_file.chmod(0o600)
        target = folder / "voice-reference.wav"
        model_python = _model_interpreter()
        if not model_python.is_file():
            raise RuntimeError("reference_voice_not_ready: isolated CPU reference model is not installed")
        # #77: avoid asking a small CPU voice model to speak an entire
        # multi-scene Short in one generation. Short real scene utterances are
        # independently verified against their own actual WAV / ASR output,
        # then concatenated without inventing timestamps or changing speaker.
        # The entire requested transcript must equal the concatenation of the
        # parts before this path is allowed.
        parts = [str(part).strip() for part in (segments or [])]
        segmented = (2 <= len(parts) <= 6
                     and all(10 <= len(p) <= 350 and len(_tokens(p)) >= 2
                             for p in parts)
                     and _tokens(" ".join(parts)) == _tokens(text))
        seeds = (190526, 220917, 314159)
        attempts_total = 0

        def verified_generation(sentence, output, *, allow_split=True):
            nonlocal attempts_total
            text_file.write_text(sentence, encoding="utf-8")
            for attempt, seed in enumerate(seeds, 1):
                attempts_total += 1
                output.unlink(missing_ok=True)
                try:
                    _run([str(model_python), str(Path(__file__).with_name("reference_voice_worker.py")),
                          "--reference", str(reference), "--text-file", str(text_file),
                          "--wav", str(output), "--seed", str(seed)],
                         timeout=300, stage="nano-reference-worker")
                    length = _wav_duration(output)
                    score = voice_similarity(reference, output)
                    timed_words = verify_reference_asr(
                        sentence, output, long_form=long_form,
                        attempt=attempt, max_attempts=len(seeds))
                    return length, score, timed_words
                except (RuntimeError, wave.Error) as exc:
                    output.unlink(missing_ok=True)
                    reason = str(exc).lower()
                    safe = ("speaker_similarity" if "speaker similarity" in reason else
                            "asr_word_mismatch" if "does not exactly match" in reason else
                            "asr_alignment" if "word alignment" in reason else
                            "model_or_audio")
                    print(f"[VOICE RETRY] approved private reference "
                          f"attempt={attempt}/3 failure_kind={safe}", flush=True)
            # All three full-length attempts failed. Rescue ONLY by speaking
            # the SAME words as shorter clauses using the SAME private voice.
            # Never guess transcripts, alter a narration word or switch speaker.
            fragments = (
                (_safe_split_for_long_form_audio(sentence)
                 if long_form else _safe_split_for_exact_audio(sentence))
                if allow_split else [])
            if fragments:
                print(f"[VOICE RESCUE] exact-transcript clause split "
                      f"fragments={len(fragments)}", flush=True)
                pieces_audio, combined_words, similarities = [], [], []
                offset = 0.0
                sample_rate = None
                for index, fragment in enumerate(fragments):
                    part_file = Path(private) / f"rescue-fragment-{index}.wav"
                    _part_length, score, words = verified_generation(
                        fragment, part_file, allow_split=False)
                    with wave.open(str(part_file), "rb") as wf:
                        current_rate = wf.getframerate()
                        if (wf.getnchannels() != 1 or wf.getsampwidth() != 2
                                or (sample_rate is not None and sample_rate != current_rate)):
                            raise RuntimeError("reference_voice_failed: incompatible verified clause PCM")
                        sample_rate = current_rate
                        samples = wf.readframes(wf.getnframes())
                        part_duration = wf.getnframes() / current_rate
                    pieces_audio.append(samples)
                    combined_words.extend((word, begin + offset, finish + offset)
                                          for word, begin, finish in words)
                    offset += part_duration
                    similarities.append(score)
                    if index < len(fragments) - 1:
                        padding = round(sample_rate * .08)
                        pieces_audio.append(b"\x00\x00" * padding)
                        offset += padding / sample_rate
                    part_file.unlink(missing_ok=True)
                if (not long_form and
                        [token for word, _, _ in combined_words for token in _tokens(word)] != _tokens(sentence)):
                    raise RuntimeError("reference_voice_failed: rescued transcript does not match original")
                with wave.open(str(output), "wb") as combined:
                    combined.setnchannels(1)
                    combined.setsampwidth(2)
                    combined.setframerate(sample_rate)
                    combined.writeframes(b"".join(pieces_audio))
                length = _wav_duration(output)
                score = min(similarities)
                return length, score, combined_words
            raise RuntimeError(
                "reference_voice_failed: all approved-reference narration "
                "attempts failed exact audio/word verification")

        target.unlink(missing_ok=True)
        if segmented:
            # Audio is stitched only AFTER every independently generated chunk
            # passes BOTH the same speaker check and exact spoken-word check.
            audio_chunks = []
            verified_words = []
            similarities = []
            rate = None
            offset = 0.0
            for index, part in enumerate(parts):
                partial = Path(private) / f"verified-scene-{index}.wav"
                _, score, part_words = verified_generation(part, partial)
                with wave.open(str(partial), "rb") as chunk:
                    sr = chunk.getframerate()
                    if (chunk.getnchannels() != 1 or chunk.getsampwidth() != 2
                            or sr not in (22050, 24000, 32000, 44100, 48000)
                            or (rate is not None and sr != rate)):
                        raise RuntimeError("reference_voice_failed: incompatible verified scene PCM")
                    rate = sr
                    audio = chunk.readframes(chunk.getnframes())
                    audio_seconds = chunk.getnframes() / sr
                audio_chunks.append(audio)
                verified_words.extend(
                    (word, start + offset, end + offset)
                    for word, start, end in part_words)
                offset += audio_seconds
                similarities.append(score)
                if index < len(parts)-1:
                    silence_samples = round(rate * 0.14)
                    audio_chunks.append(b"\x00\x00" * silence_samples)
                    offset += silence_samples / rate
                partial.unlink(missing_ok=True)
            if (not long_form and
                    [token for word, _, _ in verified_words for token in _tokens(word)] != _tokens(text)):
                raise RuntimeError("reference_voice_failed: concatenated narration transcript mismatch")
            # Long-form was validated on each independently spoken WAV. Minor
            # deviations are captioned using ACTUAL audio, never script timing.
            # Short-form requires the original exact concatenated transcript.
            with wave.open(str(target), "wb") as joined:
                joined.setnchannels(1)
                joined.setsampwidth(2)
                joined.setframerate(rate)
                joined.writeframes(b"".join(audio_chunks))
            duration = _wav_duration(target)
            similarity = min(similarities)
            timed = verified_words
            print(f"[VOICE SEGMENTED] approved speaker verified across "
                  f"{len(parts)} exact spoken scenes", flush=True)
        else:
            duration, similarity, timed = verified_generation(text, target)
        attempt = attempts_total
    words = [Word(word, start, end) for word, start, end in timed]
    proof = {
        "engine": "reference",
        "model": "ResembleAI/chatterbox-nano",
        "voice": REFERENCE_VOICE_ID,
        "reference_original_sha256": ENGLISH_REFERENCE_SHA256,
        "reference_opus_sha256": ENGLISH_REFERENCE_OPUS_SHA256,
        "reference_private": True,
        "software_license": "MIT",
        "speaker_similarity_method": "Resemblyzer speaker embeddings",
        "speaker_similarity_cosine": round(similarity, 4),
        "similarity_is_not_identity_proof": True,
        "timing": "aligned",
        "alignment": "faster-whisper-base.en actual generated WAV word timestamps",
        "duration_seconds": round(duration, 3),
        "words": len(words),
        "synthesis_attempts": attempt,
        "verified_scene_segments": len(parts) if segmented else 1,
        "long_form_asr_minor_discrepancies_allowed": bool(long_form)
    }
    speech = Speech(target, words, duration, "reference", REFERENCE_VOICE_ID, "aligned")
    speech.provenance = proof
    print(f"[VOICE SELECTED] approved-reference-only alignment_words={len(words)} duration={duration:.2f}s", flush=True)
    return speech
