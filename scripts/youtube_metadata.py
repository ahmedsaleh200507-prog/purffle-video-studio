"""YouTube Shorts upload titles: automatic, truthful and free to fall back.

This only creates text metadata AFTER an actual MP4 passes production validation.
It never modifies the video, requests upload permissions, or affects render success.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path


MAX_TITLE = 90  # YouTube allows 100 characters; leave space for edits.

_EMOJI = (
    (("snake", "serpent"), "🐍"),
    (("lightning", "thunder"), "⚡"),
    (("volcano", "volcanic", "lava"), "🌋"),
    (("desert", "burning", "fire", "flame"), "🔥"),
    (("antarctica", "glacier", "ice", "frozen"), "🧊"),
    (("ocean", "deep sea", "underwater", "marine", "waterfall", "sea"), "🌊"),
    (("cave", "underground", "hole"), "🕳️"),
    (("forest", "trees"), "🌲"),
    (("island",), "🏝️"),
)


def _clean(value: str, limit: int = MAX_TITLE) -> str:
    """One copyable line, no Markdown/quotes, safely within platform limit."""
    lines = str(value or "").splitlines()
    value = lines[0].strip() if lines else ""
    value = re.sub(r"^(?:youtube\s+shorts?\s+)?title\s*:\s*", "", value, flags=re.I)
    value = re.sub(r"^[#*\s]+", "", value)
    value = value.strip(' \'"\u201c\u201d\u2018\u2019')
    value = re.sub(r"\s+", " ", value)
    # Never allow a copied markdown fence, URL, or rogue API-key-looking token.
    if (not value or value.startswith("&#") or "http://" in value.lower()
            or "https://" in value.lower() or "sk-" in value.lower()):
        return ""
    if len(value) > limit:
        shortened = value[: limit + 1].rsplit(" ", 1)[0].rstrip(" ,:;-")
        value = shortened if len(shortened) > 20 else value[:limit].rstrip(" ,:;-")
    return value


def _fallback_title(topic: str, language: str) -> str:
    """Use the user's accurate topic as the fail-safe hook, not invented facts."""
    text = _clean(topic, limit=MAX_TITLE - 4) or ("A Curious Mystery" if language == "en" else "Ein spannendes Rätsel")
    low = text.lower()
    emoji = next((symbol for words, symbol in _EMOJI if any(w in low for w in words)), "🤯")
    if text.endswith("!"):
        return _clean(text + " " + emoji)
    if text.endswith("?"):
        return _clean(text + " " + emoji)
    return _clean(text + " " + emoji)


def _title_related(candidate: str, topic: str) -> bool:
    """Guard against an unrelated AI hook; never certify disputed claims."""
    common = set("what when where why how does do is are the a an can of in on it your its who to and with for was were really this that the most".split())
    tokens = lambda text: {t for t in re.findall(r"[a-zÀ-ÿ]{4,}", text.lower()) if t not in common}
    wanted = tokens(topic)
    return not wanted or bool(wanted & tokens(candidate))


def make_short_title(topic: str, language: str = "en", existing_title: str = "") -> str:
    """Generate one catchy, topic-grounded title; safe local fallback always works.

    Reuses the existing Groq secret if available. The optional network request
    is bounded and cannot prevent a validated MP4 from being delivered.
    """
    language = "de" if language == "de" else "en"
    fallback = _fallback_title(topic, language)
    if os.environ.get("PURFFLE_SHORTS_TITLE_AI", "1") == "0" or not os.environ.get("GROQ_API_KEY"):
        return fallback
    try:
        from groq import Groq
        client = Groq(api_key=os.environ["GROQ_API_KEY"], timeout=15.0, max_retries=0)
        system = (
            "You are an expert YouTube Shorts title editor. Return ONLY one very engaging "
            f"{'German' if language == 'de' else 'English'} title, 35-85 characters. "
            "Build curiosity using the actual video topic. Be specific and natural. "
            "Never invent facts, discoveries, danger, celebrities, scientific claims, or "
            "promise content that the source topic doesn't mention. Don't add quotes, "
            "markdown, hashtags, all-caps clickbait, or an explanation. "
            "One appropriate emoji is allowed but not required."
        )
        response = client.chat.completions.create(
            model=os.environ.get("LLM_MODEL", "openai/gpt-oss-20b"),
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps({
                    "topic": str(topic)[:500], "existing_video_title": str(existing_title)[:150],
                }, ensure_ascii=False)},
            ],
            max_completion_tokens=300,
        )
        proposal = _clean(response.choices[0].message.content)
        if proposal and 20 <= len(proposal) <= MAX_TITLE and _title_related(proposal, topic):
            return proposal
    except Exception:
        # A title-generation quota/network error is NOT a failed video.
        pass
    return fallback


def attach_title_to_video(result: dict) -> dict:
    """Write a .txt adjacent to the verified MP4, and expose title in report."""
    if result.get("status") != "ok" or not result.get("mp4"):
        return result
    video = Path(result["mp4"])
    if not video.is_file():
        return result
    existing_title = ""
    metadata_name = result.get("metadata")
    if metadata_name and Path(metadata_name).is_file():
        try:
            meta = json.loads(Path(metadata_name).read_text(encoding="utf-8"))
            existing_title = str(meta.get("title") or "")
        except (OSError, ValueError, TypeError):
            pass
    title_file = video.parent / "YouTube_Title.txt"
    if title_file.is_file():
        current = _clean(title_file.read_text(encoding="utf-8", errors="replace"))
        # Resume should preserve the original, already prepared title.
        if current:
            result.update(youtube_title=current, youtube_title_file=str(title_file))
            return result
    title = make_short_title(result.get("topic", ""), result.get("language", "en"), existing_title)
    title_file.write_text(title + "\n", encoding="utf-8")
    result.update(youtube_title=title, youtube_title_file=str(title_file))
    return result


def write_batch_titles(root: Path, results: list[dict]) -> Path:
    """Convenient single upload sheet; failed or non-existent videos get no title."""
    destination = Path(root) / "YOUTUBE_SHORTS_TITLES.txt"
    lines = ["PURFFLE - YOUTUBE SHORTS UPLOAD TITLES", "",
             "Copy each TITLE into the YouTube Shorts title field.", ""]
    count = 0
    for result in results:
        if result.get("status") != "ok" or not result.get("youtube_title"):
            continue
        video_name = result.get("mp4")
        if not video_name or not Path(video_name).is_file():
            continue
        count += 1
        lines += [
            f"VIDEO {int(result.get('index', count)):02d}",
            "TITLE: " + _clean(result["youtube_title"]),
            "MP4: " + str(video_name),
            "",
        ]
    if not count:
        lines.append("No validated MP4 titles available yet.")
    temp = destination.with_suffix(".tmp")
    temp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    temp.replace(destination)
    return destination
