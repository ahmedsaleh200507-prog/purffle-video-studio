"""Isolated reference-narrator audition: never silently replace production Piper.

This experimental tool accepts an authorized, *private local* speech WAV.
Neither the original user video nor the reference is uploaded or checked in.
An English/German Qwen3-TTS clone may resemble the reference; neither the
model nor this program can establish perceptual 'identical voice'.
Never enable on a video workflow until a real test proves speech, duration,
caption alignment, license/consent and editorial acceptability.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import wave

MODEL = "Qwen/Qwen3-TTS-12Hz-0.6B-Base"
REVISION = "5d83992436eae1d760afd27aff78a71d676296fc"
LICENSE = "Apache-2.0"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_reference(path, expected_sha256):
    p = Path(path)
    if not p.is_file() or p.is_symlink():
        raise RuntimeError("reference_voice_missing: private PCM WAV file required")
    digest = sha256(p)
    if not re.fullmatch(r"[a-f0-9]{64}", str(expected_sha256 or "")):
        raise RuntimeError("reference_voice_hash_required: pin the exact sample SHA256")
    if digest != expected_sha256:
        raise RuntimeError("reference_voice_changed: sample differs from the pinned WAV")
    if p.stat().st_size > 2_000_000:
        raise RuntimeError("reference_voice_invalid: WAV sample exceeds 2MB")
    try:
        with wave.open(str(p), "rb") as wav:
            rate, channels, width = wav.getframerate(), wav.getnchannels(), wav.getsampwidth()
            seconds = wav.getnframes() / max(1, rate)
    except (OSError, EOFError, wave.Error) as error:
        raise RuntimeError("reference_voice_invalid: unreadable WAV") from error
    if (channels != 1 or width != 2 or rate not in (16000, 24000)
            or not 6 <= seconds <= 15):
        raise RuntimeError(
            "reference_voice_invalid: require 6-15s mono 16-bit PCM at 16/24kHz")
    return {"sha256": digest, "seconds": round(seconds, 2),
            "sample_rate": rate, "size": p.stat().st_size}


def generate_audition(*, reference, expected_sha256, text, language,
                      output, transcript="", x_vector_only=False, model_loader=None):
    """Generate isolated audition, not a replacement for Piper or proof of identity."""
    voice_ref = validate_reference(reference, expected_sha256)
    if language not in ("en", "de"):
        raise RuntimeError("reference_voice_language_invalid: only en/de supported")
    if not 5 <= len(str(text).strip()) <= 500:
        raise RuntimeError("reference_voice_text_invalid: narration must be 5-500 characters")
    if not x_vector_only and not str(transcript).strip():
        raise RuntimeError("reference_voice_transcript_required: exact spoken reference text needed")
    if transcript and len(transcript) > 500:
        raise RuntimeError("reference_voice_transcript_invalid: reference text too long")
    target = Path(output)
    if target.suffix.lower() != ".wav":
        raise RuntimeError("reference_voice_output_invalid: output must be WAV")
    if target.resolve() == Path(reference).resolve():
        raise RuntimeError("reference_voice_output_invalid: refusing to overwrite source")
    if model_loader is None:
        import torch
        from qwen_tts import Qwen3TTSModel
        # No CUDA/GPU assumption on standard GitHub-hosted Ubuntu runner.
        model_loader = lambda: Qwen3TTSModel.from_pretrained(
            MODEL, revision=REVISION, device_map="cpu",
            dtype=torch.float32, attn_implementation="sdpa")
    model = model_loader()
    prompt = model.create_voice_clone_prompt(
        ref_audio=str(reference),
        ref_text=str(transcript).strip() or None,
        x_vector_only_mode=bool(x_vector_only))
    raw, sr = model.generate_voice_clone(
        text=str(text).strip(),
        language="German" if language == "de" else "English",
        voice_clone_prompt=prompt)
    if not raw or not isinstance(sr, int) or not 16000 <= sr <= 48000:
        raise RuntimeError("reference_voice_generation_failed: no valid waveform")
    import numpy as np
    import soundfile as sf
    samples = np.asarray(raw[0]).reshape(-1)
    if (not samples.size or not np.isfinite(samples).all()
            or np.max(np.abs(samples)) < 0.001
            or not 0.7 <= samples.size / sr <= 75):
        raise RuntimeError("reference_voice_generation_failed: bad waveform")
    target.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(target), samples, sr, subtype="PCM_16")
    report = {
        "state": "audition_only_unverified_similarity",
        "reference_sha256": voice_ref["sha256"],
        "reference_seconds": voice_ref["seconds"],
        "model": MODEL, "revision": REVISION, "license": LICENSE,
        "language": language, "generated_seconds": round(samples.size / sr, 2),
        "output": str(target),
        "warning": ("Not an identical-voice certificate. No source audio is "
                    "uploaded and no synchronized word boundaries are created. "
                    "This WAV must NOT enter final videos until real evaluation."),
    }
    path = target.with_suffix(".voice-report.json")
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description="Private voice reference audition (NOT production)")
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--text", required=True)
    parser.add_argument("--language", choices=("en", "de"), default="en")
    parser.add_argument("--ref-transcript", default="")
    parser.add_argument("--x-vector-only", action="store_true",
                        help="Lower fidelity audition without reference transcription")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    info = generate_audition(
        reference=args.reference, expected_sha256=args.expected_sha256,
        text=args.text, language=args.language, output=args.output,
        transcript=args.ref_transcript, x_vector_only=args.x_vector_only)
    print(json.dumps(info, ensure_ascii=False))


if __name__ == "__main__":
    main()
