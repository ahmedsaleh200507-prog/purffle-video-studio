"""Validate one of ten long-documentary inputs without starting expensive tools.

GitHub dispatch accepts ten text slots. Each must use en|topic or de|topic,
no language guesses, multiple topics, or embedded newlines. Blank slots
perform no downloads or production.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from long_generic import check_long_topic


def parse_long_slot(raw: str):
    if not isinstance(raw, str):
        raise ValueError("Slot must be text")
    raw = raw.strip()
    if not raw:
        return None
    if "|" not in raw:
        raise ValueError("Write en|Topic or de|Thema in each long-video field")
    language, topic = raw.split("|", 1)
    if language.strip().lower() not in ("en", "de"):
        raise ValueError("Language prefix must be en| or de|")
    if "|" in topic or "\n" in topic or "\r" in topic:
        raise ValueError("Each slot must contain exactly one topic")
    language = language.strip().lower()
    return language, check_long_topic(topic, language)


def choose_slot(raw: str, slot: int) -> dict:
    if not 1 <= slot <= 10:
        raise ValueError("Long-video slot must be numbered 1 through 10")
    parsed = parse_long_slot(raw)
    if not parsed:
        return {"slot": slot, "render": False}
    lang, topic = parsed
    return {"slot": slot, "render": True, "language": lang,
            "topic": topic}


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--slot", type=int, required=True)
    p.add_argument("--raw", default=None,
                   help="Local testing only; production uses environment")
    a = p.parse_args(argv)
    raw = a.raw if a.raw is not None else os.environ.get("LONG_SLOT_TOPIC", "")
    data = choose_slot(raw, a.slot)
    out_file = os.environ.get("GITHUB_OUTPUT")
    content = f"render={'true' if data['render'] else 'false'}\n"
    if data["render"]:
        content += f"language={data['language']}\n"
        content += f"topic={data['topic']}\n"
        print(f"[LONG SLOT] index={a.slot} language={data['language']} "
              f"topic={data['topic']!r}", flush=True)
    else:
        print(f"[LONG SLOT] index={a.slot} blank: no download, no render",
              flush=True)
    if out_file:
        with Path(out_file).open("a", encoding="utf8") as output:
            output.write(content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
