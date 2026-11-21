"""Small schema-constrained Groq batches for the 10-minute volcano pilot.

A single 14-chapter completion previously returned malformed/truncated JSON.
The independent long form job validates every batch before voice/render work.
"""
from __future__ import annotations

import json
import os
import re
import time
import unicodedata

TOPICS = (
    "A question from inside Earth",
    "The movement of tectonic plates",
    "Where magma comes from",
    "How magma rises",
    "What dissolved gases do",
    "Why some volcanoes explode",
    "Quiet lava versus explosive eruptions",
    "Warning signs before eruption",
    "The first seconds of an eruption",
    "Ash clouds and their dangers",
    "Lava flows and their effects",
    "How scientists monitor volcanoes",
    "What remains after an eruption",
    "What we can and cannot predict",
)
# A distinct, original documentary linking the current Ice Age search trend
# to genuine subglacial volcano science. Do NOT use Disney or third-party clips.
FIRE_AND_ICE_TOPICS = (
    "A hot volcano hidden beneath a frozen glacier",
    "How glaciers can cover volcanoes",
    "Where the magma beneath the ice comes from",
    "What happens when lava touches glacier ice",
    "Steam explosions beneath ice",
    "How volcanic heat melts ice into hidden lakes",
    "Sudden floods released from beneath glaciers",
    "Iceland as a real world example of fire under ice",
    "How volcanic ash can spread over frozen landscapes",
    "What eruption clouds mean for the sky and aviation",
    "How glaciers reshape volcanic mountains",
    "Why Earth's last glaciation was a slow natural process",
    "How scientists monitor volcanoes beneath ice",
    "Why real fire and ice science is stranger than fiction",
)


def is_fire_and_ice(topic: str) -> bool:
    lower = str(topic).casefold()
    return (any(part in lower for part in ("ice age", "glacier", "beneath ice"))
            and any(part in lower for part in ("volcan", "lava", "eruption")))


BATCH_SIZES = (4, 4, 4, 2)

CHAPTER_SCHEMA = {
    "type": "object",
    "properties": {
        "chapters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "narration": {"type": "string"},
                },
                "required": ["title", "narration"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["chapters"],
    "additionalProperties": False,
}


# Spoken English narration must be understandable to viewers and recognizable
# in independently timed real audio. Particularly difficult loanwords were
# responsible for the failure at chapter 11 of the Fire and Ice production.
# Substitute plain-language equivalents BEFORE any voice synthesis; the saved
# script, the actual audio and captions all use exactly this finalized wording.
_SPOKEN_EQUIVALENTS = (
    (r"\bj[oö]kulhlaups?\b", "sudden glacier floods"),
    (r"\bcirques?\b", "bowl shaped valleys"),
    (r"\bar[eê]tes?\b", "steep mountain ridges"),
    (r"\blahars?\b", "volcanic mudflows"),
    (r"\brhyolitic\b", "silica rich"),
    (r"\bamphitheat(?:er|re)[- ]shaped\b", "bowl shaped"),
)


def accessible_science_narration(text: str) -> str:
    """Simplify a few inaccessible technical words, never invent audio timing.

    Restricted to the fire-and-ice long documentary. This changes only future
    script text *before* the narrator speaks; no subtitle/audio falsification.
    """
    value = str(text).replace("’", "'").replace("‘", "'")
    # Unicode dash characters can be read aloud unpredictably by small TTS,
    # particularly when they combine multiple technical words.
    for dash in ("—", "–"):
        value = value.replace(dash, ", ")
    for hyphen in ("‑", "‐", "−"):
        value = value.replace(hyphen, "-")
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    for pattern, replacement in _SPOKEN_EQUIVALENTS:
        value = re.sub(pattern, replacement, value, flags=re.IGNORECASE)
    return " ".join(value.split())


def count_words(s):
    return len(re.findall(r"\b[\w'-]+\b", str(s)))


def validate_batch(data, requested_titles):
    """Treat schema-valid but incomplete, repetitive or too-short text as failure."""
    if not isinstance(data, dict) or set(data) != {"chapters"}:
        raise ValueError("script_schema_mismatch")
    raw = data["chapters"]
    if not isinstance(raw, list) or len(raw) != len(requested_titles):
        raise ValueError("script_chapter_count_mismatch")
    clean = []
    for number, (entry, name) in enumerate(zip(raw, requested_titles), 1):
        if not isinstance(entry, dict) or set(entry) != {"title", "narration"}:
            raise ValueError(f"script_invalid_chapter_object_{number}")
        title = str(entry["title"]).strip()
        narration = " ".join(str(entry["narration"]).split())
        count = count_words(narration)
        if not title or not 90 <= count <= 135:
            raise ValueError(f"script_chapter_{number}_bad_length_{count}")
        if "subscribe" in narration.lower() or "like this video" in narration.lower():
            raise ValueError("script_contains_channel_prompt")
        clean.append({"title": title, "narration": narration})
    return clean


def build_documentary(topic: str, client=None, *, sleep=time.sleep):
    if not os.environ.get("GROQ_API_KEY") and client is None:
        raise RuntimeError("GROQ_API_KEY missing")
    if client is None:
        from groq import Groq
        client = Groq(api_key=os.environ["GROQ_API_KEY"], timeout=120)
    subjects = FIRE_AND_ICE_TOPICS if is_fire_and_ice(topic) else TOPICS
    finished = []
    at = 0
    for batch_number, size in enumerate(BATCH_SIZES, 1):
        requested = subjects[at:at+size]
        start = at + 1
        instruction = (
            ("Use accessible spoken English and short, natural clauses. "
             "AVOID obscure specialist terms, accented spellings, em dashes, "
             "and complicated technical names that speech engines or viewers "
             "could mishear; use plain-language explanations instead. "
             "This is an original science documentary, NOT a film trailer. "
             "For the ice-under-volcano topic, explain real subglacial eruptions, "
             "steam, ice melt, and glacial floods with cautious accurate science. "
             "The new Ice Age: Boiling Point film trailer released November 2026 "
             "sparked interest in the theme; if mentioned, treat it only as an "
             "opening cultural reference, not as scientific evidence or a source "
             "of video footage. Do not claim a global ice age can happen overnight. "
             "Modern glacier stock cannot depict actual prehistoric history. "
             if is_fire_and_ice(topic) else "") + (
            f"Write section {start} through {at + size} of a coherent English "
            f"10-minute educational documentary called {topic!r}. "
            f"Return a JSON object with exactly {size} chapters in the order of "
            f"these numbered subject headings: "
            + "; ".join(f"{start + j}. {name}" for j, name in enumerate(requested))
            + ". Each chapter MUST contain 105-120 NEW spoken English words in "
              "the narration field. Do not abbreviate. Use clear verified general "
              "scientific explanations. No fabricated quotes, sources, numerical "
              "statistics, stage directions or requests to subscribe. "
              "Chapters should explain causal mechanisms and transition naturally. "
              "The FIRST chapter must start with an immediate intriguing hook. "
              "Last chapter concludes the film. Output JSON only."
        ))
        failure_reason = "no_valid_response"
        for attempt in range(3):
            try:
                result = client.chat.completions.create(
                    model="openai/gpt-oss-20b",
                    messages=[
                        {"role": "system", "content": (
                            "You are a careful science documentary writer. "
                            "Output JSON strictly conforming to the schema; do not shorten chapters."
                        )},
                        {"role": "user", "content": instruction},
                    ],
                    response_format={
                        "type": "json_schema",
                        "json_schema": {
                            "name": "documentary_chapters",
                            "strict": True,
                            "schema": CHAPTER_SCHEMA,
                        },
                    },
                    max_tokens=4500,
                    temperature=0.3,
                )
                choice = result.choices[0]
                if choice.finish_reason != "stop":
                    raise ValueError("script_response_truncated")
                raw = choice.message.content or ""
                parsed = json.loads(raw)
                batch = validate_batch(parsed, requested)
                if is_fire_and_ice(topic):
                    batch = [
                        {**chapter, "narration": accessible_science_narration(
                            chapter["narration"])}
                        for chapter in batch
                    ]
                    # Final saved narration is what both the private voice
                    # and actual word-aligned subtitles will speak.
                    if any(not 90 <= count_words(item["narration"]) <= 135
                           for item in batch):
                        raise ValueError("spoken_language_simplification_bad_length")
                finished.extend(batch)
                failure_reason = ""
                print(f"[SCRIPT] verified batch={batch_number}/4 chapters={len(batch)}", flush=True)
                break
            except (ValueError, IndexError, KeyError, TypeError) as exc:
                failure_reason = str(exc)[:100] or type(exc).__name__
                print(f"[SCRIPT] batch={batch_number}/4 validation retry={attempt+1}/3 "
                      f"reason={failure_reason}", flush=True)
            if attempt < 2:
                sleep(5)
        if failure_reason:
            raise RuntimeError(f"script_batch_{batch_number}_invalid_after_3_attempts: {failure_reason}")
        at += size
        if batch_number < len(BATCH_SIZES):
            sleep(5)  # Keep free-tier requests spaced; no parallel API flood.
    if len(finished) != 14:
        raise RuntimeError("Expected 14 verified chapters, never claim a complete script")
    total = sum(count_words(c["narration"]) for c in finished)
    if not 1250 <= total <= 1890:
        raise RuntimeError(f"Insufficient total narration words={total}")
    return finished
