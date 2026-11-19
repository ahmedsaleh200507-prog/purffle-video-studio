"""Separate CPU model worker for the sole approved English speaker.

This script is launched only by approved_reference_voice.py from a dedicated
Python virtualenv. It never selects a pretrained speaker or uses a fallback.
Reference and output WAV stay in private runner temp directories.
"""
from __future__ import annotations

import argparse
import math
import os
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--text-file", type=Path, required=True)
    parser.add_argument("--wav", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=190526)
    args = parser.parse_args()
    if not args.reference.is_file() or not args.text_file.is_file():
        raise RuntimeError("reference_voice_not_ready: private reference/text files missing")
    # Public CI may receive only these fixed stage labels, never actual
    # approved voice data, transcript, model error or private file paths.
    # Never fall back to a global Python when the private Chatterbox virtualenv
    # was required. Path.resolve() in the caller used to break this invariant.
    if sys.prefix == sys.base_prefix:
        raise RuntimeError("private reference model interpreter is not an active virtualenv")
    print("[VOICE SAFE STAGE] worker-start", flush=True)
    text = args.text_file.read_text(encoding="utf-8").strip()
    if not 4 <= len(text) <= 1600 or "\n" in text:
        raise RuntimeError("reference_voice_not_ready: invalid single-narrator text input")
    print("[VOICE SAFE STAGE] text-validated", flush=True)
    import numpy as np
    print("[VOICE SAFE STAGE] numpy-loaded", flush=True)
    import soundfile as sf
    print("[VOICE SAFE STAGE] soundfile-loaded", flush=True)
    import torch
    print("[VOICE SAFE STAGE] torch-loaded", flush=True)
    from chatterbox.tts_turbo import ChatterboxTurboTTS
    print("[VOICE SAFE STAGE] dependencies-loaded", flush=True)
    torch.set_num_threads(2)
    torch.manual_seed(args.seed)
    model = ChatterboxTurboTTS.from_pretrained(device="cpu", nano=True)
    print("[VOICE SAFE STAGE] model-loaded", flush=True)
    with torch.inference_mode():
        audio = model.generate(text, audio_prompt_path=str(args.reference))
    print("[VOICE SAFE STAGE] generated-waveform", flush=True)
    waveform = audio.detach().float().cpu().numpy().reshape(-1)
    rate = int(model.sr)
    if (rate not in (22050, 24000, 32000, 44100, 48000)
            or not rate <= len(waveform) <= rate * 80
            or not np.isfinite(waveform).all()
            or not (0.003 <= np.sqrt(np.mean(waveform ** 2)) <= .85)
            or np.max(np.abs(waveform)) >= 1.5):
        raise RuntimeError("reference_voice_failed: generated narration audio invalid")
    args.wav.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(args.wav), waveform, rate, subtype="PCM_16")
    os.chmod(args.wav, 0o600)
    print("[VOICE SAFE STAGE] saved-waveform", flush=True)
    print("[REFERENCE VOICE] Nano model generated audio from pinned private reference", flush=True)


if __name__ == "__main__":
    main()
