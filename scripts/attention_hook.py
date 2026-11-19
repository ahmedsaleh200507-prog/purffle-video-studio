"""Shorts opening hook: short editorial text, transparent design, kinetic entrance.

The narration, spoken-word captions, verified footage and existing watermark
policy are never modified. The pinned upstream is patched in memory only.
"""
from __future__ import annotations

import math
from pathlib import Path
import re


ACCENT = "#FFE344"
WHITE = "#F9FCFF"
DARK = "#091222"


def compact_hook_lines(text: str, language: str = "en") -> list[str]:
    """Preserve the question, with a short, accurate lightning/thunder hook.

    Other topics retain their own wording; no AI-generated factual claims and
    no generic, misleading clickbait are added.
    """
    text = " ".join(str(text or "").strip().split())
    if not text:
        return []
    simple = re.sub(r"[!?]+$", "", text).strip()
    match = re.fullmatch(
        r"why do we see\s+(.+?)\s+before\s+(?:we\s+)?hear(?:ing)?\s+(.+)",
        simple, flags=re.I)
    if match:
        flash, sound = (re.sub(r"[^\w\s-]", "", x).strip().upper()
                        for x in match.groups())
        if flash and sound and len(flash.split()) <= 3 and len(sound.split()) <= 3:
            return [f"{flash} FIRST", f"{sound} LATER", "WHY?"]
    # Keep every word of normal hook titles; focus the presentation rather
    # than inventing an unsupported replacement.
    words = text.upper().split()
    if len(words) <= 2:
        return [" ".join(words)]
    max_lines = 3
    # Balance by visual characters, not by an arbitrary first-N-words cut.
    # Total width is also checked at drawing time against the actual font.
    chars = sum(len(w) + 1 for w in words)
    target = max(11, math.ceil(chars / max_lines))
    lines, row = [], []
    for word in words:
        proposal = " ".join(row + [word])
        if row and len(proposal) > target and len(lines) < max_lines - 1:
            lines.append(" ".join(row))
            row = [word]
        else:
            row.append(word)
    if row:
        lines.append(" ".join(row))
    return lines


def accent_words(lines: list[str]) -> set[str]:
    """Highlight meaningful nouns and the question cue, not every word."""
    ignore = {
        "WHY", "WHAT", "WHEN", "WHERE", "HOW", "DO", "DOES", "DID", "ARE",
        "IS", "A", "AN", "THE", "WE", "YOU", "YOUR", "OUR", "IT", "CAN",
        "BEFORE", "AFTER", "FIRST", "LATER", "AND", "OF", "IN", "FOR", "TO",
        "WIE", "WARUM", "WIESO", "WAS", "DER", "DIE", "DAS", "EIN", "EINE",
        "IST", "SIND", "DEN", "DEM", "UND",
    }
    meaningful = []
    for line in lines:
        for token in line.split():
            bare = re.sub(r"[^\wÄÖÜẞ-]", "", token).strip()
            if bare and bare not in ignore and bare not in meaningful:
                meaningful.append(bare)
    return set(meaningful[:2]) | {"WHY?", "WARUM?"}


def _font(path, size):
    from PIL import ImageFont
    if path and Path(path).is_file():
        return ImageFont.truetype(str(path), size)
    for candidate in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    ):
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default(size=size)


def _render_hook(settings, font_path, text):
    """Transparent glow and punchy editorial typography, no black title card."""
    from PIL import Image, ImageDraw, ImageFilter
    W = int(settings.width * 0.91)
    H = min(int(settings.height * 0.34), int(settings.width * 0.56))
    W = max(220, W)
    H = max(145, H)
    lines = compact_hook_lines(text, getattr(settings, "language", "en"))
    if not lines:
        raise ValueError("Cannot render an empty opening hook")

    # Never add an opaque background or rounded black box.
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    haze = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    hdraw = ImageDraw.Draw(haze)
    hdraw.ellipse((int(W * .02), int(H * .03), int(W * .98), int(H * .96)),
                  fill=(4, 12, 23, 110))
    haze = haze.filter(ImageFilter.GaussianBlur(max(15, W // 20)))
    canvas.alpha_composite(haze)

    draw = ImageDraw.Draw(canvas)
    # Understated editorial rules frame the hook, without hiding the footage.
    pad = max(14, int(W * .06))
    rule_y = max(15, int(H * .09))
    draw.rounded_rectangle((pad, rule_y, pad + int(W * .14), rule_y + 5),
                           radius=2, fill=(255, 227, 68, 255))
    draw.ellipse((pad + int(W * .15), rule_y, pad + int(W * .15) + 5, rule_y + 5),
                 fill=(255, 255, 255, 205))
    draw.rounded_rectangle((W-pad-int(W*.12), H-rule_y-5, W-pad, H-rule_y),
                           radius=2, fill=(255, 227, 68, 230))

    base = max(26, int(settings.width * (.100 if len(lines) <= 2 else .084)))
    gap = max(6, int(base * .14))
    max_text_width = W - 2 * (pad + 3)
    height_budget = H - 2 * (rule_y + 13)

    def metrics(size):
        font = _font(font_path, size)
        ascent, descent = font.getmetrics()
        line_height = ascent + descent + gap
        widths = [draw.textlength(x, font=font) for x in lines]
        return font, line_height, max(widths), (line_height * len(lines) - gap)
    size = base
    font, line_height, widest, needed_height = metrics(size)
    while (widest > max_text_width or needed_height > height_budget) and size > 22:
        size -= 2
        font, line_height, widest, needed_height = metrics(size)

    y = int((H - needed_height) / 2) - 3
    highlights = accent_words(lines)
    sw = max(2, round(size * .055))
    for line in lines:
        tokens = line.split()
        space = draw.textlength(" ", font=font)
        widths = [draw.textlength(t, font=font) for t in tokens]
        line_w = sum(widths) + space * (len(tokens) - 1)
        x = (W - line_w) / 2
        for word, width in zip(tokens, widths):
            plain = re.sub(r"[^\wÄÖÜẞ-]", "", word)
            emphasis = (plain in highlights or word in highlights)
            # Strong dark outer stroke and soft offset shadow stay readable
            # across bright clouds, white foam, sun and city footage.
            draw.text((round(x)+3, y+5), word, font=font, fill=(0, 0, 0, 185),
                      stroke_width=sw + 2, stroke_fill=(0, 0, 0, 155))
            draw.text((round(x), y), word, font=font,
                      fill=ACCENT if emphasis else WHITE,
                      stroke_width=sw, stroke_fill=DARK)
            x += width + space
        y += line_height
    return canvas


def attention_hook_png(settings, font_path, text: str, dest: Path,
                       y_ratio: float = .15, max_lines: int = 3):
    """Drop-in replacement for pinned upstream overlays.hook_png."""
    im = _render_hook(settings, font_path, text)
    im.save(dest)
    return dest, int(settings.height * y_ratio)


_HOOK_RE = re.compile(r"overlay=x=\(W-w\)/2:y=(\d+):eof_action=pass\[vhook\]")


def kinetic_hook_filter(args: list[str]) -> list[str]:
    """Animate ONLY the existing hook overlay (small spring-in then settle).

    Keep synced captions, voice, source footage, progress bar and watermark
    untouched. If upstream filter shape changes, leave it alone.
    """
    result = list(args)
    if "-filter_complex" not in result:
        return result
    idx = result.index("-filter_complex") + 1
    if idx >= len(result):
        return result
    def replace(match):
        y = int(match.group(1))
        return ("overlay=x='(W-w)/2':"
                f"y='{y}-48*exp(-7*t)*cos(10*t)':"
                "eof_action=pass[vhook]")
    result[idx] = _HOOK_RE.sub(replace, result[idx], count=1)
    return result


def install_attention_hook(overlays):
    overlays.hook_png = attention_hook_png
