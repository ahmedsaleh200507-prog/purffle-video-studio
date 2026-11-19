"""Live CPU narrator smoke, never uploads or publishes the sample/audio."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import json
import tempfile

from english_reference_policy import approved_secret_bytes, REFERENCE_VOICE_ID
from approved_reference_voice import synthesize


def main():
    approved_secret_bytes()
    with tempfile.TemporaryDirectory(prefix="reference-live-smoke-") as work:
        # Re-check actual speaker and actual audio word timing before stock search.
        speech = synthesize(
            "Lightning flashes across the night sky.",
            Path(work) / "output",
            SimpleNamespace(language="en"))
        assert speech.voice == REFERENCE_VOICE_ID and speech.engine == "reference"
        assert speech.timing == "aligned" and len(speech.words) == 6
        assert speech.provenance.get("speaker_similarity_cosine", 0) >= .70
        assert speech.provenance["reference_private"] is True
        print("[VOICE SMOKE] Approved private English speaker produced verified "
              "real WAV and aligned words; no audio artifacts retained.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
