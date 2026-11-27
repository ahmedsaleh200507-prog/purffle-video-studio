"""Language-aware 14-chapter long documentaries on user-selected subjects.

This is isolated from Shorts, the existing tested volcano pilot and its fixed
opening. No prompt response is trusted: complete outline and every narration
batch must pass local structural, length, and uniqueness checks.
"""
from __future__ import annotations

import json
import os
import re
import time

from long_script import (
    CHAPTER_SCHEMA, count_words, is_groq_json_validation_error, validate_batch
)

OUTLINE_SCHEMA = {
    "type": "object",
    "properties": {
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "visual_search_query": {"type": "string"},
                    "visual_subject": {"type": "string"},
                },
                "required": ["title", "visual_search_query", "visual_subject"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["sections"],
    "additionalProperties": False,
}

LANGUAGES = {"en": "English", "de": "German"}
# German Piper Thorsten and approved-reference English speak at different rates.
# Measure the FINAL real narration and fail if not 9–11 minutes; no silent filler.
# Calibrated from audited CC0 Thorsten live voice: six German words in
# 2.252 seconds (~160 wpm), so 14*~113 words targets ~594 seconds.
# Actual WAV duration remains the source of truth; never pad/speed falsify.
SPOKEN_TARGET = {"en": (105, 120), "de": (108, 118)}
SPOKEN_BOUNDS = {"en": (90, 135), "de": (95, 135)}
SPOKEN_TOTAL = {"en": (1250, 1890), "de": (1300, 1890)}


def check_long_topic(raw: str, language: str) -> str:
    if language not in LANGUAGES:
        raise ValueError("Choose en or de for each long documentary")
    if not isinstance(raw, str):
        raise ValueError("Topic must be a string")
    topic = " ".join(raw.split())
    if not 8 <= len(topic) <= 180 or "|" in topic:
        raise ValueError("Long documentary topic must be 8–180 characters and contain no pipe")
    if re.search(r"(?i)(?:^|\s)(en|de)\s*\|", topic):
        raise ValueError("One topic per long video slot")
    return topic


def validate_outline(data) -> list[dict]:
    if not isinstance(data, dict) or set(data) != {"sections"}:
        raise ValueError("outline_invalid_object")
    sections = data["sections"]
    if not isinstance(sections, list) or len(sections) != 14:
        raise ValueError("outline_must_have_exactly_14_chapters")
    output = []
    seen = set()
    for section in sections:
        if not isinstance(section, dict) or set(section) != {
            "title", "visual_search_query", "visual_subject"
        }:
            raise ValueError("outline_bad_chapter_keys")
        title = " ".join(str(section["title"]).split())
        query = " ".join(str(section["visual_search_query"]).split())
        subject = " ".join(str(section["visual_subject"]).split())
        if (not 5 <= len(title) <= 110 or not 4 <= len(query) <= 85
                or not 3 <= len(subject) <= 35
                or not 1 <= len(subject.split()) <= 3
                or not 1 <= len(query.split()) <= 9
                or any("\n" in x or "|" in x for x in (title, query, subject))
                or title.casefold() in seen):
            raise ValueError("outline_bad_heading_or_visual_query")
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9 '\-]{2,34}", subject):
            raise ValueError("visual_subject_must_be_simple_english_nouns")
        seen.add(title.casefold())
        output.append({
            "title": title,
            "visual_search_query": query,
            "visual_subject": subject.lower(),
        })
    return output


def _completion(client, prompt, schema, name, *, max_tokens=3500, fallback=False):
    response_format = ({"type": "json_object"} if fallback else {
        "type": "json_schema", "json_schema": {
            "name": name, "strict": True, "schema": schema,
        },
    })
    result = client.chat.completions.create(
        model="openai/gpt-oss-20b",
        messages=[
            {"role": "system", "content":
             "You write careful, original, factually cautious documentary content. "
             "Output only a JSON object. Do not invent historical statistics, "
             "scientific discoveries, specific quotes, or event footage."},
            {"role": "user", "content": prompt},
        ],
        response_format=response_format,
        max_tokens=max_tokens,
        temperature=.2,
    )
    choice = result.choices[0]
    if choice.finish_reason != "stop":
        raise ValueError("documentary_json_truncated")
    return json.loads(choice.message.content or "")


def _retried_json(client, prompt, schema, name, validator, *,
                  sleep, max_tokens=3500):
    reason = "no_verified_response"
    for attempt in range(1, 4):
        try:
            return validator(_completion(
                client, prompt + (f"\nPrevious response was rejected: {reason}. Correct that exact issue." if attempt>1 else ""), schema, name,
                max_tokens=max_tokens, fallback=(attempt == 3)))
        except (ValueError, TypeError, KeyError, IndexError, json.JSONDecodeError) as exc:
            reason = type(exc).__name__ + ":" + str(exc)[:80]
        except Exception as exc:
            if not is_groq_json_validation_error(exc):
                raise
            reason = "groq_json_validate_failed"
        print(f"[LONG DOCUMENTARY JSON RETRY] {name} attempt={attempt}/3 "
              f"reason={reason}", flush=True)
        if attempt < 3:
            sleep(5)
    raise RuntimeError(f"{name}_unverified_after_3_attempts:{reason}")


def generate_outline(topic: str, language: str, client, *, sleep=time.sleep):
    from editorial_standard import enabled, long_brief
    language_name = LANGUAGES[language]
    prompt = (
        f"Build a non-fiction documentary outline about {topic!r} with exactly "
        f"14 distinct, numbered-in-order chapters. Write the title of each "
        f"chapter in {language_name}, not mixed language. This is not a volcano "
        f"documentary unless the topic is actually volcanoes. The story must "
        f"stay on the requested topic: opening question, coherent explanations, "
        f"examples, concrete observable evidence, and a precise conclusion. "
        f"For EVERY chapter, give a SHORT visual_search_query (2–6 English "
        f"keywords) describing actual real-world stock VIDEO footage of "
        f"the visible subject, not a claim about an invisible mechanism; "
        f"also give a visual_subject (one to three simple English nouns) "
        f"appearing in that search query, e.g. 'octopus', 'deep sea', 'mountain', "
        f"'airplane', 'castle', 'rain forest'. Use distinct, obtainable real "
        f"stock clips and avoid impossible reenactments, fictional footage, "
        f"trademarks, movie screenshots and invented images. Return one JSON "
        f"object with exactly a sections array; each item must have exactly "
        f"title, visual_search_query and visual_subject."
    )
    if enabled():
        prompt += "\n"+long_brief()
    return _retried_json(client, prompt, OUTLINE_SCHEMA,
                         "long_documentary_outline", validate_outline,
                         sleep=sleep, max_tokens=3100)


def _validate_group(data, names, language):
    if language == "en":
        return validate_batch(data, names)
    if not isinstance(data, dict) or set(data) != {"chapters"}:
        raise ValueError("script_schema_mismatch")
    rows = data["chapters"]
    if not isinstance(rows, list) or len(rows) != len(names):
        raise ValueError("script_chapter_count_mismatch")
    clean = []
    low, high = SPOKEN_BOUNDS[language]
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"title", "narration"}:
            raise ValueError("script_invalid_chapter_object")
        title = " ".join(str(row["title"]).split())
        narration = " ".join(str(row["narration"]).split())
        if not title or not low <= count_words(narration) <= high:
            raise ValueError("script_german_chapter_word_count_invalid")
        if "subscribe" in narration.lower() or "abonnier" in narration.lower():
            raise ValueError("script_contains_channel_prompt")
        clean.append({"title": title, "narration": narration})
    return clean


def build_multilingual_documentary(topic: str, language: str, client=None,
                                   *, sleep=time.sleep):
    topic = check_long_topic(topic, language)
    if client is None:
        from long_llm import get_long_client
        client = get_long_client()

    from production_checkpoint import get_script_part,put_script_part
    from editorial_standard import enabled,VERSION,long_brief,chapter_context
    version=VERSION if enabled() else "legacy"
    identity=[topic,language,version]
    outline=get_script_part("generic-outline",identity)
    if outline is not None:
        outline=validate_outline({"sections":outline})
    else:
        outline=generate_outline(topic, language, client, sleep=sleep)
        put_script_part("generic-outline",identity,outline)
    low, high = SPOKEN_TARGET[language]
    written = []
    for offset in range(0, 14, 2):
        current = outline[offset:offset+2]
        labels = " ".join(f"Section {offset+i+1}: {item['title']}."
                          for i, item in enumerate(current))
        prompt = (
            f"Write exactly 2 chapters of an original, coherent, educational "
            f"documentary about {topic!r}. Write every word of the narration "
            f"in {LANGUAGES[language]}, natural for a fluent native speaker. "
            f"The two headings, in order, are {labels} "
            f"Each chapter must contain {low} to {high} FULL spoken words "
            f"with complete sentences, never outlines or bullet points. "
            f"Use straightforward spoken language, careful scientific/historical "
            f"reasoning and avoid unsupported specific numbers, false facts, "
            f"fictional firsthand eyewitness accounts or fabricated quotations. "
            f"Do not imply modern stock clips are real footage of past events. "
            f"The first section should open with a hook only if it is section 1 "
            f"of the entire documentary. The final section should conclude "
            f"only if it is section 14. Never ask viewers to subscribe. "
            f"Return ONLY JSON with exactly chapters as an array of exactly "
            f"two objects, each with title and narration strings."
        )
        if enabled():
            prompt += "\n"+long_brief()+"\n"+chapter_context(outline,offset,written[-1]["narration"] if written else "")
        group_identity=[topic,language,current,version, written[-1]["narration"] if enabled() and written else ""]
        key=f"generic-group-{offset}"
        saved=get_script_part(key,group_identity)
        if saved is not None:
            valid=_validate_group({"chapters":saved},[p["title"] for p in current],language)
            print(f"[SCRIPT RESUME] chapters {offset+1}-{offset+2}",flush=True)
        else:
            try:
                valid = _retried_json(
                    client, prompt, CHAPTER_SCHEMA, "long_documentary_chapters",
                    lambda raw: _validate_group(
                        raw, [p["title"] for p in current], language),
                    sleep=sleep, max_tokens=3000)
            except RuntimeError as exc:
                if "unverified_after_3_attempts" not in str(exc):
                    raise
                # Smaller responses reduce truncation and word-count failures.
                # Never pad or reuse another chapter's narration.
                valid=[]
                for i,item in enumerate(current):
                    single_prompt=(
                        f"Write exactly one chapter, section {offset+i+1} of 14, "
                        f"about {topic!r}, with title {item['title']!r}. "
                        f"Use only {LANGUAGES[language]} for narration, {low} to {high} spoken words. "
                        "Use careful factual explanations, complete sentences, no invented claims, "
                        "no subscribe prompt. Return JSON with chapters containing exactly one "
                        "object with title and narration.")
                    if enabled():
                        previous=(valid[-1]["narration"] if valid else written[-1]["narration"] if written else "")
                        single_prompt+="\n"+long_brief()+"\n"+chapter_context(outline,offset+i,previous)
                    valid.extend(_retried_json(
                        client,single_prompt,CHAPTER_SCHEMA,"long_documentary_single",
                        lambda raw: _validate_group(raw,[item["title"]],language),
                        sleep=sleep,max_tokens=1800))
            put_script_part(key,group_identity,valid)
        for i, row in enumerate(valid):
            row["title"] = current[i]["title"]
            row["visual_search_query"] = current[i]["visual_search_query"]
            row["visual_subject"] = current[i]["visual_subject"]
        written.extend(valid)
        print(f"[LONG SCRIPT] language={language} validated="
              f"{len(written)}/14 chapters", flush=True)
        if offset < 12:
            sleep(5)
    count = sum(count_words(row["narration"]) for row in written)
    lo, hi = SPOKEN_TOTAL[language]
    if len(written) != 14 or not lo <= count <= hi:
        raise RuntimeError(f"Invalid long {language} script total words={count}")
    return written
