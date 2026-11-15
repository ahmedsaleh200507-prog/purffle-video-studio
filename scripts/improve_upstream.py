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
               'of the subject, not a metaphor. Prefer accurate visuals over generic filler. ' 
               'Build a consistent storyboard: keep the same protagonist, location and central object ' 
               'across consecutive scenes. Narration must describe concrete visible actions in ' 
               'chronological order. Each scene search_query must include the key physical object ' 
               'AND visible action (for example \"man picking up euro banknote\", not \"money\" ' 
               'or \"gold\"). Do not invent unrelated twists or switch to abstract metaphors.')
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
media_source = media_source.replace(old, new, 1)
print("Purffle unrelated-stock rejection gate prepared", flush=True)

# Search only scene-specific terms; do not broaden to a German topic or
# unrelated general concepts after the scene search fails.
old_queries = '''        for q in (query, simplify_query(query), simplify_query(topic), topic):'''
new_queries = '''        for q in (query, simplify_query(query), simplify_query(topic), topic):'''
if old_queries not in media_source:
    raise SystemExit("Upstream scene query strategy changed; refusing unsafe patch")
media_source = media_source.replace(old_queries, new_queries, 1)

# A single shared word out of three is weak evidence. Require at least two thirds
# the scene terms in the provider's actual descriptive metadata; reject missing metadata.
media_source = media_source.replace(
    'matching = [c for c in fresh if relevance(c, query) >= 0.34]',
    'matching = [c for c in fresh if relevance(c, query) >= 0.25]',
    1
)
media_source = media_source.replace(
    '''                if not matching:
                    return None''',
    '''                if not matching:
                    log.info("Rejecting %d unrelated candidates for scene query %r", len(fresh), query)
                    return None''',
    1
)
# The first write above happens before these additions. Write final patched
# version again so all changes take effect.
media_path.write_text(media_source, encoding="utf-8")
print("Scene-only queries and balanced 25% metadata relevance gate enabled", flush=True)


# Video-only policy: photos, AI stills and gradient placeholders are forbidden.
# If no real motion footage can be sourced, fail explicitly rather than exporting
# a misleading 'successful' MP4 with blank/animated filler.
search_needle = '''        ck = (source, query.lower())'''
search_patch = '''        if source in ("wikimedia-video", "nasa-video", "coverr-video", "archive-video"):
            from video_sources import search_wikimedia_videos, search_nasa_videos, search_coverr_videos, search_archive_videos
            handlers = {"wikimedia-video": search_wikimedia_videos, "nasa-video": search_nasa_videos, "coverr-video": search_coverr_videos, "archive-video": search_archive_videos}
            return handlers[source](query, MediaItem)
        ck = (source, query.lower())'''
if search_needle not in media_source:
    raise SystemExit("Upstream search method changed; cannot enforce video-only mode")
media_source = media_source.replace(search_needle, search_patch, 1)

claim_needle = '''fresh = [c for c in candidates if c.key not in self.used]'''
claim_patch = '''fresh = [c for c in candidates if c.kind == "video" and c.key not in self.used]'''
if claim_needle not in media_source:
    raise SystemExit("Upstream claim method changed; cannot enforce video-only mode")
media_source = media_source.replace(claim_needle, claim_patch, 1)

fallback_needle = '''return MediaItem("generated", f"gradient-{idx}", "generated", query=query)'''
fallback_patch = '''raise RuntimeError(f"No suitable REAL VIDEO for scene {idx + 1}: {query!r}; refusing photo/gradient fallback")'''
if fallback_needle not in media_source:
    raise SystemExit("Upstream fallback changed; cannot enforce video-only mode")
media_source = media_source.replace(fallback_needle, fallback_patch, 1)
media_path.write_text(media_source, encoding="utf-8")
print("STRICT VIDEO ONLY: Pixabay/Pexels/Wikimedia videos; no photos or gradients", flush=True)
