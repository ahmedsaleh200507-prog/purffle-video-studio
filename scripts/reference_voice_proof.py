"""Private, real-model narrator proof: NO VIDEO SEARCH, NO PUBLIC AUDIO ARTIFACTS.

Use on main after modifying the pinned English voice pipeline. This tests
the same scientific narration that production #81-#83 failed to synthesize.
Failure blocks any claim that the narrator has been repaired.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import tempfile

from approved_reference_voice import synthesize
from english_reference_policy import approved_secret_bytes, REFERENCE_VOICE_ID
from fact_checked_topics import ground_verified_documentary


TOPIC = "Why Do Steel Ships Float?"


def prove_real_reference_voice():
    approved_secret_bytes()
    output = ground_verified_documentary({}, TOPIC, "en", scene_count=4)
    scenes = [scene["narration"] for scene in output["scenes"]]
    assert len(scenes) == 4
    text = " ".join(scenes)
    with tempfile.TemporaryDirectory(prefix="purffle-narrator-proof-") as temp:
        speech = synthesize(
            text, Path(temp) / "render", SimpleNamespace(language="en"),
            segments=scenes)
        proof = speech.provenance
        if (speech.engine != "reference" or speech.voice != REFERENCE_VOICE_ID
                or speech.timing != "aligned" or
                proof.get("speaker_similarity_cosine", 0) < .70 or
                proof.get("reference_private") is not True or
                proof.get("verified_scene_segments") != 4 or
                not speech.audio.is_file() or len(speech.words) < 30):
            raise RuntimeError("reference_voice_failed: full narrator proof incomplete")
        print(f"[VOICE REAL PROOF PASSED] scenes=4 "
              f"actual_aligned_words={len(speech.words)} "
              f"speaker_similarity_min={proof['speaker_similarity_cosine']:.3f} "
              f"seconds={speech.duration:.2f}", flush=True)
    # Temporary audio and user-approved private prompt have both been deleted.


if __name__ == "__main__":
    prove_real_reference_voice()
