"""English voice publication policy: only the user-approved reference speaker.

The user approved one PRIVATE 10-second PCM WAV. Its SHA-256 is a *recording*
identity, NOT proof that a cloned TTS output sounds identical. No sample is
stored in the public repository.

Until a clone has been verified for real synthesis and native/forced word
alignment, never publish English production video with Piper Joe, Edge, a
female voice, or an unrelated model. German Piper Thorsten remains unchanged.
"""
from __future__ import annotations

import argparse
import os

ENGLISH_REFERENCE_SHA256 = (
    "6cc53c46241503f7c6a813ecf98f726eec38bfae33177d624b4ac9190fc41146"
)
ENGLISH_REFERENCE_SECONDS = 10.0
ENGLISH_REFERENCE_SAMPLE_RATE = 16000

# This flag describes completed implementation/testing, NOT user preference.
# The private voice asset, consistent speaker clone and speech-word alignment
# have NOT been proven or provisioned on Actions. Deliberately immutable
# false until the full reference pipeline is implemented and reviewed.
REFERENCE_PRODUCTION_READY = False


def requires_reference_only(language: str, *, strict: bool | None = None) -> bool:
    if strict is None:
        strict = os.environ.get("PURFFLE_STRICT", "0") == "1"
    return str(language).strip().lower() == "en" and bool(strict)


def enforce_english_reference_only(language: str, *, strict: bool | None = None):
    """Fail BEFORE producing speech or accepting an MP4 from a wrong speaker."""
    if not requires_reference_only(language, strict=strict):
        return
    # A future reference synthesizer needs a separate, real implementation
    # with reference hash, repeatability, voice QA and subtitle verification.
    if not REFERENCE_PRODUCTION_READY:
        raise RuntimeError(
            "reference_voice_not_ready: English video requires the user's "
            "approved 10-second reference male speaker; Piper Joe, Edge or "
            "any other fallback voice is forbidden. No verified reference "
            "voice synthesizer has been deployed to GitHub Actions.")


def topic_language(value: str) -> str:
    """Read only the explicit prefix; normal batch parsing owns inference."""
    raw = str(value).strip().casefold()
    if raw.startswith("en|") or raw.startswith("en "):
        return "en"
    if raw.startswith("de|") or raw.startswith("de "):
        return "de"
    # The normal batch parser defaults to English unless it finds German.
    # Use that parser when installed; otherwise refuse an ambiguous topic.
    raise ValueError("English reference preflight needs explicit en| / de| topic")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", required=True)
    args = parser.parse_args()
    enforce_english_reference_only(topic_language(args.topic), strict=True)
    print("[VOICE POLICY] Reference-only English check passed or German voice unchanged")


if __name__ == "__main__":
    main()
