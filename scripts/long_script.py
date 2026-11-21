"""Small schema-constrained Groq batches for the 10-minute volcano pilot.

A single 14-chapter completion previously returned malformed/truncated JSON.
The independent long form job validates every batch before voice/render work.
"""
from __future__ import annotations

import json
import os
import re
import time

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
    finished = []
    at = 0
    for batch_number, size in enumerate(BATCH_SIZES, 1):
        requested = TOPICS[at:at+size]
        start = at + 1
        instruction = (
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
        )
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
                    reasoning_effort="low",
                    max_completion_tokens=4500,
                    temperature=0.3,
                )
                choice = result.choices[0]
                if choice.finish_reason != "stop":
                    raise ValueError("script_response_truncated")
                raw = choice.message.content or ""
                parsed = json.loads(raw)
                batch = validate_batch(parsed, requested)
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
