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


def is_groq_json_validation_error(exc: Exception) -> bool:
    """Recognize exactly the invalid generated-JSON error returned by Groq.

    This 400 is a model-output generation failure, not a request/schema bug.
    Do NOT retry authentication errors, rate limits, unavailable models, or
    network problems under the same broad handler.
    """
    body = getattr(exc, "body", None)
    code = getattr(exc, "code", None)
    if isinstance(body, dict):
        details = body.get("error", body)
        if isinstance(details, dict):
            code = code or details.get("code")
    return (code == "json_validate_failed" or
            ("json_validate_failed" in str(exc) and
             "Failed to validate JSON" in str(exc)))


def _validate_spoken_batch(batch, topic: str):
    if not is_fire_and_ice(topic):
        return batch
    result = [
        {**chapter, "narration": accessible_science_narration(
            chapter["narration"])}
        for chapter in batch
    ]
    # Saved script, real audio and word-aligned SRT must all use the same text.
    if any(not 90 <= count_words(item["narration"]) <= 135
           for item in result):
        raise ValueError("spoken_language_simplification_bad_length")
    return result


def build_documentary(topic: str, client=None, *, sleep=time.sleep):
    if client is None:
        from long_llm import get_long_client
        client = get_long_client()

    subjects = FIRE_AND_ICE_TOPICS if is_fire_and_ice(topic) else TOPICS

    def request_verified_group(requested, start, batch_number, depth=0):
        """Validate actual model output, then adaptively split only on failure.

        Four 100+ word sections can intermittently trigger Groq's
        json_validate_failed 400 with an empty failed_generation. Splitting
        the same sequence into 2+2 or single-chapter requests uses fewer
        output tokens, preserving every heading and the full 14 chapters.
        No fabricated text or unverified partial script is ever returned.
        """
        size = len(requested)
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
            f"Write section {start} through {start+size-1} of a coherent English "
            f"10-minute educational documentary called {topic!r}. "
            f"Return a JSON object with exactly {size} chapters in the order of "
            f"these numbered subject headings: "
            + "; ".join(f"{start+j}. {name}" for j, name in enumerate(requested))
            + ". Each chapter MUST contain 105-120 NEW spoken English words in "
              "the narration field. Do not abbreviate. Use clear verified general "
              "scientific explanations. No fabricated quotes, sources, numerical "
              "statistics, stage directions or requests to subscribe. "
              "Chapters should explain causal mechanisms and transition naturally. "
              "The FIRST chapter must start with an immediate intriguing hook "
              "only if this is section 1 of the whole film. "
              "The last chapter must conclude the film only if this is section 14. "
              "Output JSON only."
        ))
        failure_reason = "no_valid_response"
        for attempt in range(1, 4):
            # For a very small group, if strict JSON Schema is repeatedly
            # rejected, use the provider's JSON object mode. Local validation
            # still enforces the exact same schema, chapter count and length.
            response_format = (
                {"type": "json_object"}
                if size <= 2 and attempt == 3
                else {"type": "json_schema", "json_schema": {
                    "name": "documentary_chapters", "strict": True,
                    "schema": CHAPTER_SCHEMA,
                }}
            )
            try:
                result = client.chat.completions.create(
                    model="openai/gpt-oss-20b",
                    messages=[
                        {"role": "system", "content": (
                            "You are a careful science documentary writer. "
                            "Return ONLY one JSON object with a chapters array. "
                            "Every array element must contain only title and narration. "
                            "Keep the required number of sections and spoken word count."
                        )},
                        {"role": "user", "content": instruction},
                    ],
                    response_format=response_format,
                    max_tokens=4500 if size >= 3 else 2300,
                    temperature=0.2 if attempt > 1 else 0.3,
                )
                choice = result.choices[0]
                if choice.finish_reason != "stop":
                    raise ValueError("script_response_truncated")
                parsed = json.loads(choice.message.content or "")
                verified = _validate_spoken_batch(
                    validate_batch(parsed, requested), topic)
                print(f"[SCRIPT] verified group={start}-{start+size-1} "
                      f"batch={batch_number}/4 depth={depth} "
                      f"chapters={len(verified)}", flush=True)
                return verified
            except (ValueError, IndexError, KeyError, TypeError) as exc:
                failure_reason = str(exc)[:100] or type(exc).__name__
            except Exception as exc:
                if not is_groq_json_validation_error(exc):
                    # A 400 invalid model JSON is recoverable. All other API
                    # exceptions must retain their own error semantics.
                    raise
                failure_reason = "groq_json_validate_failed"
            print(f"[SCRIPT RETRY] batch={batch_number}/4 "
                  f"group={start}-{start+size-1} attempt={attempt}/3 "
                  f"reason={failure_reason}", flush=True)
            if attempt < 3:
                sleep(5)
        if size > 1:
            cut = size // 2
            print(f"[SCRIPT SPLIT] batch={batch_number}/4 "
                  f"range={start}-{start+size-1} "
                  f"into={len(requested[:cut])}+{len(requested[cut:])} "
                  f"last_error={failure_reason}", flush=True)
            left = request_verified_group(
                requested[:cut], start, batch_number, depth+1)
            sleep(5)
            right = request_verified_group(
                requested[cut:], start+cut, batch_number, depth+1)
            return left + right
        raise RuntimeError(
            f"script_batch_{batch_number}_invalid_after_3_attempts: "
            f"section={start} reason={failure_reason}")

    finished = []
    at = 0
    for batch_number, size in enumerate(BATCH_SIZES, 1):
        requested = subjects[at:at+size]
        group = request_verified_group(requested, at+1, batch_number)
        if len(group) != size:
            raise RuntimeError(f"script_batch_{batch_number}_incomplete")
        finished.extend(group)
        at += size
        if batch_number < len(BATCH_SIZES):
            sleep(5)  # Avoid parallel/free-tier API flooding.
    if len(finished) != 14:
        raise RuntimeError("Expected 14 verified chapters, never claim a complete script")
    total = sum(count_words(c["narration"]) for c in finished)
    if not 1250 <= total <= 1890:
        raise RuntimeError(f"Insufficient total narration words={total}")
    return finished
