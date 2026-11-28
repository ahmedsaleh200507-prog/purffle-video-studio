"""Locked Shorts-only reference style: Anton, white, active yellow, black outline.

Use the same pinned upstream renderer for both successful and recovery Shorts.
The SRT sidecar retains the actual transcript and measured timings.
"""
from dataclasses import replace
from pathlib import Path

SETTINGS=dict(caption_style="bold",caption_position="center",caption_font="",
              caption_fontsize=0,caption_max_words=3,caption_uppercase=True,
              caption_emphasis=False,caption_emoji=False)

def lock_settings(settings):
    return replace(settings,**SETTINGS)

def install_style(overlays):
    # Fixed palette and center (56% from top). No per-topic emphasis or
    # entrance animation. Active-word enlargement matches the reference.
    overlays.CAPTION_STYLES["bold"]=overlays.CapStyle(
        fill="#FFFFFF",active="#FFE11A",spoken=None,stroke="#000000",
        stroke_ratio=.10,shadow=True,box=None,glow=None,
        active_scale=1.12,pop=False,font="anton",emphasis=None)
    overlays.CENTER_Y["center"]=.56
    original=overlays.needs_ass
    if getattr(original, "_purffle_locked_caption_policy", False):
        return
    def needs_ass(settings):
        if settings.language.split("-")[0] in ("en","de") and settings.width<settings.height:
            return False
        return original(settings)
    needs_ass._purffle_locked_caption_policy = True
    overlays.needs_ass=needs_ass

def recovery_captions(words,total,language,work):
    from purffle_shorts.config import Settings
    from purffle_shorts import overlays
    from purffle_shorts.timing import caption_chunks,srt
    settings=lock_settings(replace(Settings.from_env(),language=language,
                                    resolution=(1080,1920),fps=30))
    install_style(overlays)
    chunks=caption_chunks(words,settings.caption_max_words,total=total)
    if not chunks:
        raise RuntimeError("No measured Shorts caption chunks")
    font,_=overlays.resolve_font(settings,"anton")
    renderer=overlays.PillowCaptions(settings,overlays.CAPTION_STYLES["bold"],font,
                                      labels=None,emphasis=None)
    playlist=renderer.build(chunks,total,Path(work)/"reference-captions")
    return playlist,renderer.band_y,srt(chunks)
