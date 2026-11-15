"""Apply a small, checked improvement to upstream Purffle's scene search prompts.

Keep upstream's rendering, scene splitting, captions and timing intact.
"""
from pathlib import Path
import purffle_shorts.script as script

path = Path(script.__file__)
source = path.read_text(encoding="utf-8")
needle = '- search_query: 1-4 English words describing concrete, filmable stock footage for that scene (e.g. "octopus underwater", "old library books"). No abstract words.'
replacement = ('- search_query: 2-4 English words for stock footage depicting EXACTLY this scene. '
               'Keep the central SUBJECT visibly present in EVERY query, including the hook and transitions '
               '(e.g. for black holes use "black hole space", "black hole accretion disk", '
               '"black hole event horizon"; NEVER use "castle", "island", "clock", '
               '"person falling" or unrelated metaphorical footage). '
               'For abstract science, search for literal scientific visualization or animation '
               'of the subject, not a metaphor. Prefer accurate visuals over generic filler.')
if needle not in source:
    raise SystemExit("Upstream prompt changed; refusing to silently patch an unknown version")
path.write_text(source.replace(needle, replacement, 1), encoding="utf-8")
print("Purffle per-scene subject-anchored visual prompts enabled", flush=True)
