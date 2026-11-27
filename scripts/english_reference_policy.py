"""Legacy reference artifact verification; V4 production uses fixed Piper voices.

The approved original 10.0s PCM WAV SHA256 identifies the speaker recording.
The 24kbps Opus version is delivered only through a private GitHub Actions
secret, never a commit, workflow input, artifact or printed log.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import os

ENGLISH_REFERENCE_SHA256 = "6cc53c46241503f7c6a813ecf98f726eec38bfae33177d624b4ac9190fc41146"
ENGLISH_REFERENCE_OPUS_SHA256 = "af686af58b15ff2842829d42217bc852d834acef5720d813b25136527b90bcf0"
ENGLISH_REFERENCE_SECONDS = 10.0
ENGLISH_REFERENCE_SAMPLE_RATE = 16000
REFERENCE_VOICE_ID = "approved-reference-male-" + ENGLISH_REFERENCE_SHA256[:16]

# This means source-code integration exists, NOT that a runner has successfully
# generated, aligned and compared cloned speech. Live production must prove all
# of those checks independently.
REFERENCE_PRODUCTION_READY = False


def requires_reference_only(language: str, *, strict: bool | None = None) -> bool:
    # English speaker selection cannot be weakened by removing PURFFLE_STRICT.
    return False  # V4 explicitly selects Piper Joe; legacy private reference stays dormant.


def approved_secret_bytes(*, source: str | None = None) -> bytes:
    """Fail closed without logging, copying or accepting another voice sample."""
    value = os.environ.get("PURFFLE_REFERENCE_OPUS_B64", "") if source is None else source
    if not value:
        raise RuntimeError(
            "reference_voice_not_ready: approved private sample is not installed as "
            "GitHub Actions secret PURFFLE_REFERENCE_OPUS_B64. No other English "
            "speaker is permitted.")
    if len(value) > 48000 or len(value) < 500:
        raise RuntimeError("reference_voice_not_ready: approved private sample secret has invalid length")
    try:
        raw = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        raise RuntimeError("reference_voice_not_ready: approved private sample secret is not base64") from None
    if hashlib.sha256(raw).hexdigest() != ENGLISH_REFERENCE_OPUS_SHA256:
        raise RuntimeError("reference_voice_not_ready: supplied speaker recording fingerprint differs")
    if not 20000 <= len(raw) <= 36000 or not raw.startswith(b"OggS"):
        raise RuntimeError("reference_voice_not_ready: approved 10-second Opus recording invalid")
    return raw


def enforce_english_reference_only(language: str, *, strict: bool | None = None):
    if requires_reference_only(language, strict=strict):
        approved_secret_bytes()


def topic_language(value: str) -> str:
    raw = str(value).strip().casefold()
    if raw.startswith("en|") or raw.startswith("en "):
        return "en"
    if raw.startswith("de|") or raw.startswith("de "):
        return "de"
    raise ValueError("English reference preflight needs explicit en| / de| topic")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", required=True)
    args = parser.parse_args()
    enforce_english_reference_only(topic_language(args.topic), strict=True)
    from local_voice import provenance
    info=provenance(topic_language(args.topic))
    print(f"[VOICE POLICY] locked {info['engine']}:{info['model']}; no reference secret required")


if __name__ == "__main__":
    main()
