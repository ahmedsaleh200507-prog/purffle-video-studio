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

# A high resolution or vertical aspect ratio must not compensate for unrelated tags.
# The original _claim accepts the highest score even when relevance is zero.
import purffle_shorts.media as media
media_path = Path(media.__file__)
media_source = media_path.read_text(encoding="utf-8")
old = '''            else:
                best = max(fresh, key=lambda c: _score(c, need, self.s.orientation, query))
            self.used.add(best.key)'''
new = '''            else:
                # Pixabay/Pexels metadata is imperfect, but never knowingly select a
                # completely unrelated result just because its format scores well.
                matching = [c for c in fresh if relevance(c, query) >= 0.34]
                if not matching:
                    return None
                best = max(matching, key=lambda c: _score(c, need, self.s.orientation, query))
            self.used.add(best.key)'''
if old not in media_source:
    raise SystemExit("Upstream media selection changed; cannot apply relevance gate safely")
media_path.write_text(media_source.replace(old, new, 1), encoding="utf-8")
print("Purffle unrelated-stock rejection gate enabled", flush=True)
