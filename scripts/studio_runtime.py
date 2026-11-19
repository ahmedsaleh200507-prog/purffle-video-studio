"""Strict runtime adapter for the audited upstream; never modifies installed source files.

Only the four upstream modules below are coupled to this adapter. A changed upstream
must be reviewed and the digests deliberately refreshed before it can render anything.
"""
from __future__ import annotations

from dataclasses import dataclass
import asyncio
import hashlib
import importlib.util
import json
import math
import os
import signal
import threading
from pathlib import Path
import time
from urllib.parse import urlsplit

from media_validation import portrait_crop_allowed

UPSTREAM_COMMIT = "514fd2547227b98d951dfc1489fc8c7ce72f1b68"
UPSTREAM_HASHES = {
    "script.py": "715baf30a21362a2013fb0dd6d80431f156b6c9a77d5f4d710a322966b894faf",
    "media.py": "2d3f6d1941a83bcbed2327de3696f58c15526618c8b51eceeff49fa76a1c8c21",
    "render.py": "7ce32dbd7e81be4f2606707afe8cb50346ab62d768553771fce5da7addf71671",
    "pipeline.py": "d3eb51f9cf877194800ef92811d96ed5199825d63a65bfaf5ddf08d06de7e4b3",
}
SCENE_FIELDS = ("main_character", "object", "action", "location", "time", "visual_search_query")
_INSTALLED = False


def verify_upstream(root=None):
    if root is None:
        spec = importlib.util.find_spec("purffle_shorts")
        if spec is None or spec.origin is None:
            raise RuntimeError("Pinned purffle-shorts is not installed")
        root = Path(spec.origin).parent
    root = Path(root)
    for filename, expected in UPSTREAM_HASHES.items():
        actual = hashlib.sha256((root / filename).read_bytes()).hexdigest()
        if actual != expected:
            raise RuntimeError(f"Unaudited upstream {filename}; install commit {UPSTREAM_COMMIT}")
    return UPSTREAM_COMMIT


def _redact(value):
    text = str(value)
    for key in ("GROQ_API_KEY", "PIXABAY_API_KEY", "PEXELS_API_KEY", "COVERR_API_KEY", "EUROPEANA_API_KEY", "GITHUB_TOKEN", "GH_TOKEN", "HF_TOKEN"):
        secret = os.getenv(key, "")
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return text


def _atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(_redact(json.dumps(data, indent=2, ensure_ascii=False, default=str)), encoding="utf-8")
    temp.replace(path)


def _native_portrait_scale(quality, target_width, target_height):
    """Actual crop-to-output scale from measured dimensions (no metadata trust)."""
    width, height = int(quality["width"]), int(quality["height"])
    if width <= 0 or height <= 0 or target_width <= 0 or target_height <= 0:
        return float("inf")
    crop_width = min(width, height * target_width / target_height)
    return max(target_width / crop_width, target_height / height)


def _scene_data(raw):
    """No guessed scene requirements: the writer must explicitly provide the plan."""
    if not isinstance(raw, dict):
        raise ValueError("Scene must include a structured visual plan")
    missing = [name for name in SCENE_FIELDS if name not in raw or not isinstance(raw[name], str)]
    if missing:
        raise ValueError("Missing structured scene fields: " + ", ".join(missing))
    data = {name: raw[name].strip() for name in SCENE_FIELDS}
    if not data["visual_search_query"] or not data["action"] or not data["object"]:
        raise ValueError("Scene requires visible object/subject, action and English visual_search_query")
    if len(data["visual_search_query"]) > 300:
        raise ValueError("Visual scene query exceeds 300 characters")
    return data


def contextual_scene_plans(raw, topic):
    """A small, auditable set of truthful establishing shots for hard-to-film science.

    These are NOT footage of the narrated event. The final report labels every
    such shot 'illustrative_context'; metadata, CLIP, native crop, motion and
    license checks remain mandatory. No generic unrelated filler is allowed.
    """
    data = _scene_data(raw)
    subject = (data["object"] + " " + data["visual_search_query"]).lower()
    title = topic.lower()
    ideas = []

    def add(obj, action, query):
        if query.lower() != data["visual_search_query"].lower():
            plan = dict(data, main_character="", object=obj, action=action,
                        location="", visual_search_query=query)
            if query not in {row["visual_search_query"] for row in ideas}:
                ideas.append(plan)

    # Retain the visible class of object whenever possible, not an invented
    # precise vessel, microorganism, location or invisible physical process.
    if any(x in subject for x in ("aircraft", "avenger", "torpedo plane", "naval plane", "airplane")):
        add("airplane", "flying", "airplane flying sky")
        if "bermuda" in title:
            add("ocean", "ambient", "ocean waves")
    elif "cave" in subject or "cavern" in subject or "höhle" in title:
        add("cave", "ambient", "cave interior")
        add("cave", "ambient", "cave stalactites")
    elif any(x in subject for x in ("algae", "sonar", "microorganism", "bacteria", "sediment")):
        if any(x in title for x in ("marian", "ozean", "ocean", "meer", "biolumines")):
            add("ocean", "ambient", "deep ocean underwater")
            add("ocean", "ambient", "ocean waves at night")
        elif any(x in title for x in ("see", "lake")):
            add("lake", "ambient", "lake water ripples")
            add("lake", "ambient", "lake surface")
    elif "harar" in subject and any(x in title for x in ("äthiop", "ethiop")):
        # Never label a generic desert video as footage of an unverified park.
        add("desert", "ambient", "desert landscape")
        add("geothermal landscape", "ambient", "volcanic desert landscape")
    elif "dune" in subject or ("sand" in subject and any(x in title for x in ("wüste", "desert"))):
        add("sand dunes", "ambient", "sand dunes desert")
        add("desert", "ambient", "desert landscape")
    elif "glacier" in subject or ("meltwater" in subject and "antarkt" in title):
        add("glacier", "ambient", "glacier ice")
        add("waterfall", "ambient", "waterfall flowing")
    elif "lake bottom" in subject:
        add("lake", "ambient", "lake water surface")

    # Bounded attempts and no duplicate discovery queries.
    return ideas[:2]


def thematic_scene_plans(raw, topic):
    """Prefer real, filmable B-roll closely related to the VIDEO'S topic.

    A narrated invisible process or rare historical moment does not require a
    literal shot. Curated subject families keep the fallback honest: a
    forest shot may illustrate the Tunguska landscape but is NOT claimed to
    depict the original explosion. No generic random clips are allowed.
    """
    data = _scene_data(raw)
    title = topic.lower()
    # These alternatives represent visible context, not any alleged event.
    # One subject per clip helps stock API metadata retrieval and CLIP checks.
    families = (
        # The user can narrate a hypothetical event without pretending to have
        # literal footage. Astronomy uses REAL night-sky/telescope recordings,
        # not a fabricated recording of somebody falling into a black hole.
        (("black hole", "event horizon", "singularity", "cosmic mystery"),
         (("sky", "night sky stars"), ("star", "stars night sky"),
          ("telescope", "observatory telescope"), ("sky", "milky way night sky"))),
        (("tsunami", "tidal wave", "giant wave", "ocean disaster"),
         (("wave", "storm waves"), ("wave", "ocean waves"),
          ("coast", "ocean coastline"), ("ocean", "rough ocean sea"))),
        (("earth stopped", "earth stop", "planet earth", "earth spin", "earth rotation"),
         (("earth", "earth from space"), ("cloud", "clouds moving sky"),
          ("sky", "night sky stars"), ("earth", "earth horizon from space"))),
        (("bermuda", "triangle mystery", "lost ships", "lost planes"),
         (("ocean", "ocean waves"), ("ship", "ship sailing sea"),
          ("airplane", "airplane flying sky"), ("ocean", "ocean aerial view"))),
        (("abandoned cit", "ghost town", "empty city", "deserted city", "abandoned town"),
         (("building", "abandoned building"), ("street", "empty city street"),
          ("ruins", "abandoned ruins"), ("city", "empty city streets"))),
        (("hurricane", "cyclone", "typhoon", "tropical storm", "eye of a storm"),
         (("storm", "storm clouds"), ("cloud", "storm clouds moving"),
          ("ocean", "rough ocean sea"), ("tree", "trees blowing in wind"))),
        (("biolumines", "ocean glow", "sea glow", "ocean light", "meer nachts"),
         (("ocean", "ocean waves at night"), ("ocean", "ocean waves"),
          ("coast", "sea coastline at night"), ("ocean", "underwater sea"))),
        (("underwater lake", "underwater lakes", "brine pool"),
         (("ocean", "deep ocean underwater"), ("seafloor", "underwater seafloor"),
          ("ocean", "ocean seabed"), ("water", "underwater sea"))),
        (("deepest part of the ocean", "deepest ocean", "ocean pressure", "deep sea", "deepest part"),
         (("ocean", "deep ocean underwater"), ("ocean", "ocean waves"),
          ("submarine", "submarine underwater"), ("ocean", "underwater sea"))),
        (("volcano", "volcanic", "volkan"),
         (("volcano", "volcano erupting"), ("lava", "volcanic lava"),
          ("volcano", "volcano landscape"), ("lightning", "lightning storm"))),
        # #70: a literal tree-root action is not necessary to explain why
        # lightning repeatedly strikes tall isolated objects. Keep the
        # footage genuinely related: actual storms, lightning and trees.
        (("lightning", "thunderbolt", "blitzschlag", "blitze"),
         (("lightning", "lightning storm"), ("cloud", "storm clouds"),
          ("tree", "trees blowing in wind"), ("sky", "dark storm sky"))),
        (("snake", "serpent", "yılan"),
         (("snake", "snake slithering"), ("snake", "snake in nature"),
          ("snake", "snake close up"), ("island", "tropical island"))),
        (("antarctica", "antarctic", "antarkt"),
         (("glacier", "glacier ice"), ("iceberg", "iceberg floating"),
          ("ice", "polar ice"), ("snow", "snow landscape"))),
        (("cave", "cavern", "höhle", "magara", "mağara"),
         (("cave", "cave interior"), ("cave", "cave stalactites"),
          ("cave", "cave formations"), ("cave", "underground cave"))),
        (("forest", "trees", "pine", "orman"),
         (("forest", "forest trees"), ("tree", "pine trees"),
          ("tree", "twisted tree branches"), ("forest", "forest aerial view"))),
        (("siberia", "tunguska", "meteor explosion"),
         (("forest", "forest trees"), ("forest", "forest aerial view"),
          ("tree", "fallen trees forest"), ("forest", "pine forest"))),
        (("desert", "burning hole", "darvaza", "wüste", "krater"),
         (("fire", "burning fire flames"), ("desert", "desert landscape"),
          ("flames", "fire flames"), ("desert", "desert aerial view"))),
    )
    # Filmable scene-specific subjects take priority when backed by the title,
    # but all fallbacks must be connected to a recognized subject family.
    selected = next((visuals for triggers, visuals in families
                     if any(trigger in title for trigger in triggers)), ())
    plans = []
    seen = {data["visual_search_query"].lower()}
    for obj, query in selected:
        if query.lower() in seen:
            continue
        seen.add(query.lower())
        plans.append(dict(data, main_character="", object=obj, action="ambient",
                          location="", visual_search_query=query))
    return plans[:4]


class StrictVisuals:
    """Sequential candidate validation keeps CPU, download and API usage bounded."""
    def __init__(self, settings, used_keys=None, *, registry=None, downloader=None, quality=None, matcher=None):
        from video_sources import ProviderRegistry
        from media_validation import VideoDownloader, QualityValidator, SceneMatcher
        self.s = settings
        if getattr(settings, "offline", False):
            raise RuntimeError("Offline/synthetic visuals are forbidden in strict production")
        self.registry = registry if registry is not None else ProviderRegistry()
        self.downloader = downloader if downloader is not None else VideoDownloader(Path("media_cache/downloads"))
        self.quality = quality if quality is not None else QualityValidator(min_short_side=720)
        self.matcher = matcher if matcher is not None else SceneMatcher()
        self.sources = [x for x in settings.visual_sources if x in self.registry.enabled]
        self.credits = set()
        self.used = set(used_keys or ())
        self.state_path = Path(os.getenv("FOOTAGE_USED_PATH", "media_cache/used-media.json"))
        try:
            state = json.loads(self.state_path.read_text()) if self.state_path.exists() else {}
        except (ValueError, OSError) as exc:
            raise RuntimeError("Cannot read footage duplicate ledger") from exc
        self.used.update(state.get("keys", []))
        self.used_urls = set(state.get("urls", []))
        self.used_hashes = set(state.get("hashes", []))
        self.report = {"state": "searching", "upstream_commit": UPSTREAM_COMMIT,
                       "policy": "real video; verified license; native source short side >=720; local visual validation",
                       "sources": self.registry.health(), "scenes": [], "provider_events": []}
        print("[SOURCE HEALTH] " + _redact(json.dumps(self.report["sources"], ensure_ascii=False)), flush=True)
        self._save()

    def _save(self):
        self.report["sources"] = self.registry.health()
        self.report["provider_events"] = list(self.registry.events)
        path = os.getenv("FOOTAGE_REPORT")
        if path:
            _atomic_json(path, self.report)

    def _remember(self, item, url_key, digest):
        self.used.add(item.key)
        self.used_urls.add(url_key)
        self.used_hashes.add(digest)
        _atomic_json(self.state_path, {"keys": sorted(self.used), "urls": sorted(self.used_urls),
                                      "hashes": sorted(self.used_hashes)})

    def for_scene(self, idx, query, image_prompt, topic, need, dest_dir):
        from media_validation import SceneSpec, reject_offtopic_science_source
        from video_sources import LicenseValidator
        try:
            data = _scene_data(json.loads(image_prompt))
        except (ValueError, TypeError) as exc:
            self.report["state"] = "failed"
            self.report["error"] = "Missing structured scene plan"
            self._save()
            raise RuntimeError("Missing structured scene plan; refusing broad topic fallback") from exc
        # Recover an explicit landmark from a descriptive LLM query. The
        # provider may otherwise return generic stones and the strict metadata
        # gate rejects even correctly tagged Stonehenge footage.
        descriptive = data["visual_search_query"].lower()
        if ("stone circle" in descriptive and "england" in descriptive
                and "stonehenge" in topic.lower()):
            data["visual_search_query"] = "Stonehenge standing stones"
        # Prefer verifiable atmospheric B-roll over an invented actor for a
        # sky-looking-up establishing shot. Stock libraries have plentiful
        # moving skies but rarely tag the exact age/gender/gaze of a person.
        # Restrict this fallback to a sky-focused shot; do not weaken actor
        # requirements for human actions elsewhere in the story.
        initial_query = data.get("visual_search_query", "").lower()
        initial_action = data.get("action", "").lower()
        if ("sky" in initial_query and ("looking up" in initial_query
                or "look up" in initial_query or "gazing" in initial_query)
                and "sky" in (data.get("object", "") + " " + initial_query).lower()
                and any(word in initial_action for word in ("look", "gaze", "watch", "stare", "observ"))):
            data["main_character"] = ""
            data["object"] = "sky"
            data["action"] = "clouds moving"
            data["visual_search_query"] = "blue sky clouds"
            print(f"[SCENE B-ROLL] scene={idx+1} actor gaze replaced with verifiable sky footage", flush=True)
        # Neural/physiological explanations are not directly filmable in stock footage.
        # Show the real animal instead; the narration conveys the invisible process.
        # Keep metadata, CLIP, license, motion and 720p checks intact.
        abstract = (data.get("visual_search_query", "") + " " + data.get("object", "")).lower()
        if ("dolphin" in abstract or "delfin" in abstract) and any(
                term in abstract for term in ("brain", "neural", "hemisphere", "cerebral")):
            data["main_character"] = ""
            data["object"] = "dolphin"
            data["action"] = "swimming"
            data["location"] = "ocean"
            data["visual_search_query"] = "dolphin swimming underwater"
            print(f"[SCENE B-ROLL] scene={idx+1} invisible dolphin brain activity replaced with filmable dolphin footage", flush=True)
        # Hybrid stock-first planning: a scientific concept belongs in narration,
        # not in a literal stock-video search. Preserve a concrete visible subject.
        invisible = ("brain", "neural", "neuron", "hemisphere", "molecule",
                     "microscopic", "atom", "photon", "memory", "thought",
                     "consciousness", "oxygen exchange", "electrical signal")
        search_text = data["visual_search_query"].lower()
        if any(term in search_text for term in invisible):
            subject = data.get("object", "").strip()
            # Prefer a concrete known visual subject from the original query.
            concrete = ("dolphin", "whale", "shark", "turtle", "bird", "dog",
                        "cat", "human", "person", "ocean", "sea", "sky",
                        "cloud", "forest", "tree", "river", "sunset", "sunrise")
            chosen = next((word for word in concrete if word in search_text.split()), None)
            if chosen and (not subject or any(term in subject.lower() for term in invisible)):
                subject = chosen
            if subject and not any(term in subject.lower() for term in invisible):
                data["main_character"] = ""
                data["object"] = subject
                data["action"] = "swimming" if subject.lower() in ("dolphin", "whale", "shark", "turtle") else "moving"
                data["visual_search_query"] = (subject + " " + data["action"])[:120]
                print(f"[STOCK-FIRST] scene={idx+1} abstract query simplified to {data['visual_search_query']!r}", flush=True)
        spec = SceneSpec.from_dict(data)
        scene = {"index": idx + 1, "plan": data, "required_seconds": need,
                 "status": "searching", "rejections": []}
        self.report["scenes"].append(scene)
        scene_start = time.monotonic()
        # Each scene has a bounded shared budget across all search strategies.
        # Without this, exact scene + five fallbacks can exhaust the entire
        # 25-minute worker timeout before subsequent scenes are attempted.
        attempt_deadline = min(scene_start + 75,
                               getattr(self, "_shot_deadline", float("inf")))
        max_candidates = max(1, min(12, int(os.getenv("CANDIDATES_PER_SOURCE", "4"))))
        for source in self.sources:
            if time.monotonic() >= attempt_deadline:
                break
            # Search a concise, subject-focused variant when verbose camera/action
            # directions cause stock providers to return unrelated footage.
            queries = [data["visual_search_query"]]
            short_query = " ".join(part for part in
                                   (data.get("object", ""), data.get("location", ""))
                                   if part).strip()
            # Preserve strict action-specific searches for ordinary scenes.
            # Only landmark footage benefits from a shorter subject query.
            landmark_terms = ("stonehenge", "machu picchu", "giza", "easter island", "moai")
            landmark_scene = any(name in queries[0].lower() for name in landmark_terms)
            # Kitchen-doorway footage is often tagged with short stock terms;
            # retain the original exact search and add a focused alternative.
            if "kitchen doorway" in queries[0].lower():
                queries.append("person entering kitchen")
                queries.append("walking through doorway")
            # Use the scene's own object/action as a fallback for ordinary
            # stock searches too. Keep the strict per-candidate metadata and
            # frame checks, rather than accepting unrelated footage.
            if ("kitchen doorway" in queries[0].lower()
                    and short_query and short_query.lower() != queries[0].lower()):
                queries.append(short_query[:120])
            # Stock APIs index short subject phrases better than long scene prose.
            # Try these automatically, while retaining the same metadata, license,
            # quality and frame-verification gates for every candidate.
            if not landmark_scene:
                subject = data.get("object", "").strip()
                action = data.get("action", "").strip()
                if subject:
                    queries.append(subject[:90])
                if subject and action:
                    queries.append((subject + " " + action)[:120])
                if short_query:
                    queries.append(short_query[:120])
            # V4: cinematic natural-scene search expansion. Stock catalogues
            # index simple visual subjects much better than long AI descriptions.
            # These alternatives are only discovery queries: the original
            # structured scene still controls license, metadata, motion and
            # frame-level visual verification.
            if not landmark_scene and not data.get("main_character", "").strip():
                natural_query = (data.get("visual_search_query", "") + " "
                                 + data.get("object", "")).lower()
                if "droplet" in natural_query or "water drop" in natural_query:
                    queries.extend(["water droplets sunlight", "water drops in sunlight",
                                    "sunlight reflecting on water", "water drops close up"])
                elif "sunlight" in natural_query and ("lake" in natural_query or "water" in natural_query):
                    queries.extend(["sunlight reflecting on water", "sun rays over lake",
                                    "sunlight on water surface"])
                elif "sky" in natural_query or "cloud" in natural_query:
                    queries.extend(["blue sky clouds", "clouds moving sky",
                                    "sunlight through clouds"])
                elif "sunset" in natural_query or "sunrise" in natural_query:
                    queries.extend(["sunrise sky", "sunset horizon", "golden hour sky"])
            # Avoid repeated API requests for identical queries.
            queries = list(dict.fromkeys(queries))
            if landmark_scene:
                if short_query and short_query.lower() != queries[0].lower():
                    queries.append(short_query[:120])
                # A named landmark is more searchable than a generated action
                # description. Keep strict metadata, license, resolution and
                # visual validation unchanged for every returned candidate.
                for landmark in landmark_terms:
                    if landmark in queries[0].lower() and landmark not in {q.lower() for q in queries}:
                        queries.append(landmark)
                        break
            candidates = []
            seen_candidates = set()
            for search_query in queries:
                for candidate in self.registry.search(source, search_query):
                    if candidate.key not in seen_candidates:
                        seen_candidates.add(candidate.key)
                        candidates.append(candidate)
                if time.monotonic() >= attempt_deadline:
                    break
            print(f"[SOURCE CHECK] {source}: {len(candidates)} candidates scene={idx+1}", flush=True)
            ranked = []
            for item in candidates:
                parts = urlsplit(item.url)
                url_key = parts.netloc.lower() + parts.path
                try:
                    if item.kind != "video" or item.key in self.used or url_key in self.used_urls:
                        raise ValueError("non_video_or_duplicate")
                    if item.width > 0 and item.height > 0 and min(item.width, item.height) < 720:
                        raise ValueError(f"Known source below 720 short side: {item.width}x{item.height}")
                    if not LicenseValidator.validate(item.extra.get("license")):
                        raise ValueError("Unverified or incompatible candidate license")
                    license_info = item.extra.get("license") or {}
                    # Source IDs and source-page slugs can reveal an unrelated
                    # planet even when the provider's short metadata says
                    # 'volcano magma'. The #69 archive clip is one such case.
                    reject_offtopic_science_source(
                        topic, " ".join((
                            str(item.id), str(item.text),
                            str(license_info.get("source_page", "")))))
                    if hasattr(self.matcher, "validate_metadata"):
                        score = self.matcher.validate_metadata(spec, item.text)
                    elif hasattr(self.matcher, "metadata_score"):
                        score = self.matcher.metadata_score(spec, item.text)
                        if score < .45:
                            raise ValueError(f"Unrelated metadata (score {score:.3f})")
                    else:
                        score = 0.0  # injected test matchers have no metadata model
                    ranked.append((score, item, url_key))
                except Exception as exc:
                    reason = _redact(f"{type(exc).__name__}: {exc}")[:450]
                    scene["rejections"].append({"source": source, "id": item.id, "reason": reason,
                                                "stage": "metadata_preflight"})
                    print(f"[REJECTED FOOTAGE] scene={idx+1} provider={source} id={item.id} preflight={reason}", flush=True)
            # Provider orientation/resolution ordering must never hide a more
            # relevant result outside the bounded download shortlist.
            def crop_rank(item):
                """Known native 9:16 footage first; unknown sizes still get probed."""
                if item.width <= 0 or item.height <= 0:
                    return 1
                required_width = getattr(self.s, "width", 720)
                required_height = getattr(self.s, "height", 1280)
                ratio = required_width / required_height
                crop_width = min(item.width, item.height * ratio)
                return 0 if crop_width >= required_width and item.height >= required_height else 2

            ranked.sort(key=lambda row: (crop_rank(row[1]), -row[0], row[1].rank,
                                          -int(row[1].height > row[1].width),
                                          -min(row[1].width, row[1].height)))
            for score, item, url_key in ranked[:max_candidates]:
                if time.monotonic() >= attempt_deadline:
                    scene["rejections"].append({"source": source, "reason": "scene_budget_exhausted"})
                    break
                path, digest = None, None
                try:
                    path = self.downloader.download(item.url)
                    digest = self.downloader.digest(path)
                    if digest in self.used_hashes:
                        raise ValueError("duplicate content hash")
                    quality = self.quality.validate(path, need=need + 0.1)
                    # Source HD is not enough: portrait cropping of 1920x1080
                    # leaves only ~608x1080 native pixels for a 720x1280 output.
                    # Reject upscaling rather than reporting false native 720p.
                    required_width = getattr(self.s, "width", 720)
                    required_height = getattr(self.s, "height", 1280)
                    native_scale = _native_portrait_scale(quality, required_width, required_height)
                    quality["portrait_crop_scale"] = round(native_scale, 5)
                    # Prefer native portrait clips. Permit a tiny, explicitly
                    # reported enlargement when cropping real 1080p landscape:
                    # 1920x1080 -> 720x1280 needs about 1.185x, common in Shorts.
                    # Never accept low-res video or unlimited fake HD scaling.
                    if not portrait_crop_allowed(native_scale):
                        raise ValueError(
                            "insufficient_native_resolution: 9:16 crop would upscale beyond safe limit "
                            f"{quality.get('width')}x{quality.get('height')} source "
                            f"to {required_width}x{required_height}"
                        )
                    match = self.matcher.match(path, spec, metadata=item.text, duration=need)
                    item.path = path
                    item.width, item.height = int(quality["width"]), int(quality["height"])
                    item.duration = float(quality["duration"])
                    item.extra.update({"quality": quality, "match": match, "start": 0.0,
                                       "strict_validated": True, "sha256": digest})
                    license_info = item.extra.get("license", {})
                    attribution = license_info.get("attribution") or item.credit
                    if not attribution:
                        raise ValueError("Missing license provenance/attribution")
                    self.credits.add(attribution)
                    self._remember(item, url_key, digest)
                    scene.update({"status": "selected", "source": source, "id": item.id,
                                  "source_url": item.url, "downloaded_file": str(path),
                                  "sha256": digest, "quality": quality, "match": match,
                                  "license": license_info,
                                  "crop": {"focus_x": match.get("crop_focus_x", .5),
                                           "effective_source_width": round(min(item.width, item.height * 9 / 16)),
                                           "effective_source_height": round(min(item.height, item.width * 16 / 9)),
                                           "upscaled_after_crop": native_scale > 1.0001,
                                           "crop_scale": round(native_scale, 4)}})
                    self._save()
                    print(f"[SELECTED FOOTAGE] scene={idx+1} provider={source} id={item.id} "
                          f"actual={item.width}x{item.height} visual_score={match.get('visual_score')} "
                          f"license={license_info.get('id')}", flush=True)
                    return item
                except Exception as exc:
                    # A rejected 4K file must not accumulate until it fills the CI disk.
                    # Preserve anything referenced by accepted footage, including a
                    # duplicate hash reached through another URL.
                    if path is not None and digest is not None and digest not in self.used_hashes:
                        try:
                            Path(path).unlink(missing_ok=True)
                            Path(path).with_suffix(".json").unlink(missing_ok=True)
                        except OSError:
                            pass  # aggregate cache budget still fails safely when full
                    reason = _redact(f"{type(exc).__name__}: {exc}")[:450]
                    scene["rejections"].append({"source": source, "id": item.id,
                                                "reason": reason, "stage": "download_quality_or_visual"})
                    print(f"[REJECTED FOOTAGE] scene={idx+1} provider={source} id={item.id} reason={reason}", flush=True)
            self._save()
        scene["status"] = "failed"
        self.report["state"] = "failed"
        self.report["error"] = f"No verified real video for scene {idx+1}"
        self._save()
        raise RuntimeError(f"No suitable verified REAL VIDEO for scene {idx+1}: {data['visual_search_query']!r}")

    def for_scenes(self, jobs, topic, dest_dir, progress=None):
        """One independently verified clip per scene; retry with truthful B-roll.

        The failed exact attempts remain in search_attempts, while the final
        report has exactly one 'selected' record per logical scene.
        """
        Path(dest_dir).mkdir(parents=True, exist_ok=True)
        items = []
        for idx, (query, prompt, need) in enumerate(jobs):
            self._shot_deadline = time.monotonic() + 210
            report_start = len(self.report["scenes"])
            mode = "exact_scene"
            try:
                item = self.for_scene(idx, query, prompt, topic, need, dest_dir)
            except RuntimeError as first_error:
                if "No suitable verified REAL VIDEO" not in str(first_error):
                    raise
                try:
                    original_data = _scene_data(json.loads(prompt))
                except (ValueError, TypeError):
                    raise first_error
                original = original_data["visual_search_query"]
                subject = original_data.get("object", "").strip()
                replans = []
                if subject and len(subject.split()) <= 3 and subject.lower() != original.lower():
                    shorter = dict(original_data, main_character="", location="",
                                   action="swimming" if subject.lower() in (
                                       "dolphin", "whale", "shark", "fish", "turtle", "seal") else "moving",
                                   visual_search_query=subject[:90])
                    replans.append(("subject_search", shorter))
                replans.extend(("illustrative_context", p)
                               for p in contextual_scene_plans(original_data, topic))
                replans.extend(("thematic_context", p)
                               for p in thematic_scene_plans(original_data, topic))
                item = None
                last_error = first_error
                seen_queries = {original.lower()}
                for next_mode, plan in replans:
                    candidate_query = plan["visual_search_query"]
                    if candidate_query.lower() in seen_queries:
                        continue
                    seen_queries.add(candidate_query.lower())
                    print(f"[AUTO REPLAN] scene={idx+1} mode={next_mode} "
                          f"query={original!r} -> {candidate_query!r}", flush=True)
                    self.report["state"] = "searching"
                    self.report.pop("error", None)
                    try:
                        item = self.for_scene(idx, candidate_query,
                                              json.dumps(plan), topic, need, dest_dir)
                        mode = next_mode
                        break
                    except RuntimeError as retry_error:
                        if "No suitable verified REAL VIDEO" not in str(retry_error):
                            raise
                        last_error = retry_error
                if item is None:
                    self.report["state"] = "failed"
                    self._save()
                    raise first_error from last_error

            attempts = self.report["scenes"][report_start:]
            selected = [row for row in attempts
                        if row.get("index") == idx + 1 and row.get("status") == "selected"]
            if len(selected) != 1:
                raise RuntimeError(f"Scene {idx+1} has no single verified footage selection")
            final = selected[0]
            final["visual_mode"] = mode
            if mode in ("illustrative_context", "thematic_context"):
                final["illustrative_not_exact_event"] = True
                final["requested_query"] = original
                print(f"[VERIFIED CONTEXTUAL B-ROLL] scene={idx+1} mode={mode} "
                      f"visual={final['plan']['visual_search_query']!r} "
                      "is illustrative, not literal event footage", flush=True)
            if len(attempts) > 1:
                final["search_attempts"] = [
                    {"query": row.get("plan", {}).get("visual_search_query", ""),
                     "status": row.get("status", "unknown"),
                     "rejections": row.get("rejections", [])}
                    for row in attempts if row is not final
                ]
                self.report["scenes"][report_start:] = [final]
            self._save()
            items.append(item)
            if progress:
                progress((idx + 1) / len(jobs))
        self.report["state"] = "footage_ready"
        self.report.pop("error", None)
        self._save()
        return items


def strict_prepare_segment(item, seconds, idx, settings, work):
    """Render only the exact stretch that was visually checked, with no looping."""
    from purffle_shorts import ffmpeg
    from purffle_shorts.render import _encode_args, _grade
    if item.kind != "video" or not item.path or not item.extra.get("strict_validated"):
        raise RuntimeError("Render refused unvalidated footage or generated/still content")
    if item.duration < seconds + 0.05:
        raise RuntimeError("Source too short; refusing footage loop")
    W, H, F = settings.width, settings.height, settings.fps
    measured_scale = _native_portrait_scale(
        {"width": item.width, "height": item.height}, W, H)
    if not portrait_crop_allowed(measured_scale):
        raise RuntimeError(
            "insufficient_native_resolution: portrait crop exceeds the shared bounded upscale limit")
    focus = float(item.extra.get("match", {}).get("crop_focus_x", 0.5))
    if not math.isfinite(focus):
        raise RuntimeError("Invalid crop focus")
    focus = max(0, min(1, focus))
    crop_width = min(item.width, item.height * W / H)
    crop_height = min(item.height, item.width * H / W)
    item.extra["crop"] = {"focus_x": focus, "effective_source_width": round(crop_width),
                          "effective_source_height": round(crop_height),
                          "upscaled_after_crop": measured_scale > 1.0001,
                          "crop_scale": round(measured_scale, 4)}
    # Keep the subject's horizontal focus; vertically centre when a wide crop is required.
    cover = (f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,"
             f"crop={W}:{H}:x='max(0,min(iw-ow,iw*{focus:.5f}-ow/2))':y='(ih-oh)/2',setsar=1")
    out = Path(work) / f"seg{idx:02d}.mp4"
    ffmpeg.run(["-threads", "2", "-filter_threads", "1", "-ss", "0", "-i", str(item.path),
                "-t", f"{seconds:.3f}", "-an", "-vf", f"{cover},fps={F}{_grade(settings)}",
                *_encode_args(settings, final=False), "-threads", "2", "-frames:v", str(max(2, round(seconds*F))), str(out)],
               label=f"validated segment {idx}", timeout=240)
    return out


def bounded_ffmpeg_args(args):
    """Limit decoder/filter/encoder threads independently for small CI runners."""
    result = ["-filter_threads", "1", "-filter_complex_threads", "1"]
    for arg in args[:-1]:
        if arg == "-i":
            result.extend(["-threads", "2"])
        result.append(arg)
    result.extend(["-threads", "2", args[-1]])
    return result


def collect_edge_chunks(communicate, timeout_seconds=70):
    """Collect the short native Edge stream while propagating async failures.

    edge-tts 7.3.1's synchronous queue adapter can hang after its worker raises,
    because no completion sentinel is enqueued on errors. Using its public async
    stream directly avoids that queue and its executor entirely.
    """
    async def collect():
        chunks, audio_bytes = [], 0
        async for chunk in communicate.stream():
            chunks.append(chunk)
            if chunk.get("type") == "audio":
                audio_bytes += len(chunk.get("data", b""))
            if len(chunks) > 5000 or audio_bytes > 16 * 1024 * 1024:
                raise RuntimeError("Edge speech exceeded short-video memory budget")
        return chunks

    async def bounded():
        return await asyncio.wait_for(collect(), timeout=float(timeout_seconds))

    return asyncio.run(bounded())


def strict_edge(text, out, settings):
    """German-only fallback. English Edge synthesis is never permitted."""
    if settings.language == "en":
        raise RuntimeError("Generic English Edge narrators removed: approved private reference required")
    import edge_tts
    from purffle_shorts.tts import EDGE_VOICES, _pick_voice
    from purffle_shorts.timing import Word
    from purffle_shorts.utils import with_retries
    voice = _pick_voice(settings, EDGE_VOICES[settings.language])
    path = Path(out) / "voice.mp3"

    def attempt():
        communicate = edge_tts.Communicate(text, voice, rate=settings.tts_rate,
                                          boundary="WordBoundary", connect_timeout=10, receive_timeout=45)
        chunks = collect_edge_chunks(communicate)
        words = []
        audio_bytes = 0
        with path.open("wb") as stream:
            for chunk in chunks:
                if chunk["type"] == "audio":
                    stream.write(chunk["data"])
                    audio_bytes += len(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    start = chunk["offset"] / 1e7
                    words.append(Word(chunk["text"], start, start + chunk["duration"] / 1e7))
        if not audio_bytes or not words:
            path.unlink(missing_ok=True)
            raise RuntimeError("Edge returned no audio or native word boundaries")
        return path, words, voice

    return with_retries(attempt, attempts=2, label=f"bounded Edge {voice}")


class _SpeechDeadline(BaseException):
    """Escape upstream retry loops, which catch ordinary Exception subclasses."""


def with_voice_deadline(synthesize, timeout_seconds=180, stage="Edge TTS"):
    """Bound the whole Edge stage, including upstream retry/backoff time.

    Actions runs the worker on Linux's main thread. Refuse unsupported invocation
    instead of silently running synthesis without the promised deadline.
    """
    if threading.current_thread() is not threading.main_thread() or not hasattr(signal, "setitimer"):
        raise RuntimeError(f"{stage} deadline requires a Linux/POSIX main-thread worker")
    timeout_seconds = max(1, min(180, float(timeout_seconds)))
    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)
    started = time.monotonic()

    def expired(signum, frame):
        raise _SpeechDeadline()

    signal.signal(signal.SIGALRM, expired)
    try:
        signal.setitimer(signal.ITIMER_REAL, timeout_seconds)
        try:
            return synthesize()
        except _SpeechDeadline as exc:
            raise RuntimeError(f"{stage} deadline exceeded ({timeout_seconds:g}s); no silent fallback permitted") from exc
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        if previous_timer[0] > 0:
            remaining = max(0.000001, previous_timer[0] - (time.monotonic() - started))
            signal.setitimer(signal.ITIMER_REAL, remaining, previous_timer[1])


def with_edge_deadline(synthesize, timeout_seconds=180):
    return with_voice_deadline(synthesize, timeout_seconds, stage="Edge TTS")


def _validate_free_speech(speech, engine, language=None):
    if speech.engine != engine or not speech.words or not str(speech.voice):
        raise RuntimeError("Narration engine or native word boundaries are invalid")
    if speech.timing not in (("native", "aligned") if engine == "edge" else ("aligned",)):
        raise RuntimeError("Narration lacks verified native/aligned word timing")
    if not math.isfinite(speech.duration) or speech.duration <= 0:
        raise RuntimeError("Narration duration is invalid")
    previous_start = -1
    for word in speech.words:
        if (not math.isfinite(word.start) or not math.isfinite(word.end)
                or word.start < previous_start or word.start < 0
                or word.end <= word.start or word.end > speech.duration + .25):
            raise RuntimeError("Narration word boundaries are invalid")
        previous_start = word.start
    if not Path(speech.audio).is_file() or Path(speech.audio).stat().st_size == 0:
        raise RuntimeError("Narration audio is missing")
    if engine == "reference":
        from english_reference_policy import REFERENCE_VOICE_ID, ENGLISH_REFERENCE_SHA256
        proof = getattr(speech, "provenance", {})
        if (language != "en" or speech.voice != REFERENCE_VOICE_ID
                or proof.get("engine") != "reference"
                or proof.get("voice") != REFERENCE_VOICE_ID
                or proof.get("reference_original_sha256") != ENGLISH_REFERENCE_SHA256
                or proof.get("reference_private") is not True
                or proof.get("alignment") !=
                    "faster-whisper-base.en actual generated WAV word timestamps"
                or float(proof.get("speaker_similarity_cosine", 0)) < .70):
            raise RuntimeError("English narration reference identity/word alignment proof invalid")
    if engine == "piper":
        proof = getattr(speech, "provenance", {})
        if proof.get("alignment") != "native_phoneme_samples":
            raise RuntimeError("Piper narration has no native sample alignment provenance")
        # Only German local Piper is permitted. All English generic model
        # allowlist entries have been physically removed.
        approved = {"de": ("de_DE-thorsten-medium", "CC0-1.0")}
        expected = approved.get(language)
        if (expected is None or proof.get("model") != expected[0]
                or speech.voice != expected[0]):
            raise RuntimeError("Piper model/voice differs from the approved locked narrator")
        license_info = proof.get("license", {})
        digest = proof.get("model_sha256", "")
        if (not isinstance(license_info, dict) or license_info.get("id") != expected[1]
                or not str(license_info.get("url", "")).startswith("https://")
                or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest)
                or not str(proof.get("model_url", "")).startswith("https://")):
            raise RuntimeError("Piper model license/hash provenance is incomplete")


def speak_with_free_fallback(screenplay, work, settings, edge_synthesize, local_synthesize):
    """Use Edge/Piper only in non-reference production (or German)."""
    from english_reference_policy import enforce_english_reference_only
    enforce_english_reference_only(settings.language)
    if settings.offline or settings.tts_engine != "edge" or settings.language not in ("de", "en"):
        raise RuntimeError("Strict production requires free Edge/local narration in de/en")
    male_lock = os.getenv('PURFFLE_NARRATOR_LOCK', '0') == '1'
    report = {"state": "synthesizing", "language": settings.language,
              "narrator_lock": male_lock, "attempts": []}
    voice_report = os.getenv("VOICE_REPORT")
    if not voice_report and os.getenv("FOOTAGE_REPORT"):
        voice_report = str(Path(os.environ["FOOTAGE_REPORT"]).with_name("voice-report.json"))
    if not voice_report:
        voice_report = str(Path(work) / "voice-report.json")

    def save():
        _atomic_json(voice_report, report)

    save()
    if settings.language == "en":
        # Absolute English-only speaker identity: NO Piper Joe, LJSpeech,
        # Edge, alternative voice, local default or fallback, even non-strict.
        from approved_reference_voice import synthesize as approved_synthesize
        started = time.monotonic()
        try:
            speech = with_voice_deadline(
                lambda: approved_synthesize(
                    screenplay.narration, Path(work) / "approved-reference-voice", settings),
                timeout_seconds=900, stage="Approved private reference narrator")
            _validate_free_speech(speech, "reference", "en")
            report["attempts"].append({
                "engine": "reference", "status": "ok",
                "seconds": round(time.monotonic()-started, 3)})
            report.update(state="ready", engine="reference", voice=speech.voice,
                          timing=speech.timing, duration=speech.duration,
                          word_count=len(speech.words),
                          provenance=getattr(speech, "provenance", {}))
            save()
            return speech
        except Exception as exc:
            report["attempts"].append({
                "engine": "reference", "status": "failed",
                "seconds": round(time.monotonic()-started, 3),
                "error": _redact(f"{type(exc).__name__}: {exc}")[:500]})
            report["state"] = "failed"
            save()
            raise RuntimeError(
                "reference_voice_failed: only approved private English narrator "
                "can be used; no alternate English speaker") from exc

    # A locked narrator must never randomly change between Edge and Piper or
    # revert to the old female LJSpeech voice after a timeout. Keep one local,
    # reproducible identity per language for every successful upload.
    engines = ((("piper", local_synthesize, "Locked male Piper narrator"),)
               if male_lock else
               (("edge", edge_synthesize, "Edge TTS"),
                ("piper", local_synthesize, "Local Piper TTS")))
    for engine, synthesize, stage in engines:
        started = time.monotonic()
        try:
            timeout = os.getenv("EDGE_TTS_TIMEOUT_SECONDS", "180") if engine == "edge" else 180
            speech = with_voice_deadline(synthesize, timeout_seconds=timeout, stage=stage)
            _validate_free_speech(speech, engine, settings.language)
            report["attempts"].append({"engine": engine, "status": "ok", "seconds": round(time.monotonic()-started, 3)})
            report.update(state="ready", engine=engine, voice=speech.voice, timing=speech.timing,
                          duration=speech.duration, word_count=len(speech.words),
                          provenance=getattr(speech, "provenance", {}))
            save()
            print(f"[VOICE SELECTED] engine={engine} voice={speech.voice} timing={speech.timing}", flush=True)
            return speech
        except Exception as exc:
            reason = _redact(f"{type(exc).__name__}: {exc}")[:600]
            report["attempts"].append({"engine": engine, "status": "failed", "seconds": round(time.monotonic()-started, 3), "error": reason})
            save()
            print(f"[VOICE FAILED] engine={engine} reason={reason}", flush=True)
    report["state"] = "failed"
    save()
    if male_lock:
        raise RuntimeError("Locked male narrator unavailable; refusing to substitute a female or different voice")
    raise RuntimeError("Free narration failed for both Edge and approved local Piper; see voice-report.json")


def install():
    global _INSTALLED
    if _INSTALLED:
        return
    verify_upstream()
    import purffle_shorts.script as script
    import purffle_shorts.media as media
    import purffle_shorts.render as render
    import purffle_shorts.pipeline as pipeline
    import purffle_shorts.ffmpeg as ffmpeg
    import purffle_shorts.tts as tts

    @dataclass
    class PlannedScene(script.Scene):
        main_character: str = ""
        object: str = ""
        action: str = ""
        location: str = ""
        time: str = ""
        visual_search_query: str = ""

    original_normalize = script.normalize
    original_prompt = script.build_prompt
    original_speak = pipeline.Studio._speak
    original_ffmpeg_run = ffmpeg.run

    def ffmpeg_run(args, **kwargs):
        return original_ffmpeg_run(bounded_ffmpeg_args(args), **kwargs)

    def normalize(data, subject, style, language):
        from fact_checked_topics import ground_lightning_explainer
        # Generic LLM rules alone did not prevent #70 inventing an Elm Street
        # oak tree hit 12 times and an unreferenced 300,000-volt measurement.
        # For this well-defined educational topic use a NOAA-grounded concise
        # script with shootable B-roll rather than publish a fictional event.
        from media_first import active_palette, align_script_to_palette
        palette = active_palette()
        data = ground_lightning_explainer(
            data, subject, language,
            scene_count=len(palette.plans) if palette else None)
        from fact_checked_topics import ground_verified_documentary
        data = ground_verified_documentary(
            data, subject, language,
            scene_count=len(palette.plans) if palette else None)
        # The verified video palette is authoritative for visual planning.
        # Narration may explain abstract facts without requiring exact footage.
        data = align_script_to_palette(data, palette)
        raw_scenes = data.get("scenes") or []
        if not raw_scenes or len(raw_scenes) > 6:
            raise ValueError("A strict video needs 1–6 explicit scenes")
        prepared, plans = [], []
        for raw in raw_scenes:
            plan = _scene_data(raw)
            if not str(raw.get("narration", "")).strip():
                raise ValueError("Scene narration is empty")
            plans.append(plan)
            prepared.append({**raw, "search_query": plan["visual_search_query"],
                             "image_prompt": json.dumps(plan, ensure_ascii=False)})
        result = original_normalize({**data, "scenes": prepared}, subject, style, language)
        if len(result.scenes) != len(plans):
            raise ValueError("Upstream discarded a structured scene")
        for scene, plan in zip(result.scenes, plans):
            for name, value in plan.items():
                setattr(scene, name, value)
        return result

    def build_prompt(*args, **kwargs):
        system, user = original_prompt(*args, **kwargs)
        user += """\n\nSTRICT REAL-FOOTAGE PLAN (these rules replace earlier visual-query/image instructions):
Every scene MUST additionally contain strings main_character, object, action, location,
time, visual_search_query. These values are ALWAYS English. Use empty main_character if
there is no human/animal character; use empty time when irrelevant. A visible subject
in object (including a natural subject such as ocean), and a concrete action are required. search_query MUST equal visual_search_query. Set
image_prompt to an empty string: images and synthetic imagery are not permitted.
visual_search_query must use concise searchable stock-video tags (ideally 2–5 English words), e.g. dolphin swimming underwater. Never include invisible processes in footage queries.
Preserve the user's concrete story, action, currency and chronology; do not replace
banknotes with gold, people with devices or actions with metaphors. Keep the same
character and object descriptions across adjacent scenes. Describe real recordable
motion, never diagrams, animation, visualizations, text-only shots or generic filler.
IMPORTANT: Every proposed scene must be achievable using ordinary real-world
stock camera footage. NEVER request microscopic air molecules, molecular-scale
Rayleigh scattering, invisible photons, scientific simulations, diagrams, or
other subjects that ordinary cameras cannot film. For explanations of invisible
physics, show directly filmable related real phenomena instead (blue sky,
sunlight through clouds, atmospheric haze, sunset sky), and narrate the invisible
mechanism accurately without pretending the footage depicts molecules.
Choose search-friendly English subject/action descriptions commonly used as
stock-video titles and tags. Prefer diverse visually relevant footage over
unfindable literal representations of abstract scientific concepts.
HYBRID STOCK-FIRST: First outline the essential truthful facts of the topic, then choose only common, directly filmable stock shots for every scene, then write narration that explains those facts while the shots support them.
FACTUAL CLAIMS FOR PUBLIC EDUCATIONAL VIDEOS: Never invent a named person,
street, town, research study, measurement, number, date, record, count,
eyewitness event, or experiment to make a generic science topic dramatic.
Never turn a generic 'why/how' question into a supposedly witnessed story.
Without a provided or verified source, use well-established general
explanations rather than precise numerical anecdotes or made-up quotations.
For lightning safety, do not recommend observing storms outside or
sheltering under trees. Ground lightning facts in NOAA/NWS guidance
where possible and keep the video filmable with real storms, clouds and
tall objects, not roots conducting a visible electrical charge. A shot need not literally depict invisible mechanisms. Avoid over-specific footage requests; prioritize diverse concrete shots. Do not sacrifice factual accuracy just to match footage. Narration must be compatible with these visible actions. Do not invent factual claims or an ending
for an underspecified real event.
For educational, science, documentary, or explanatory topics, EVERY scene
including the final scene must stay on the requested subject. Finish with a
relevant visual conclusion, not a social-media call to action. NEVER generate
scenes of people commenting, liking, subscribing, sharing, clicking buttons,
scrolling social media, or watching a video unless the user explicitly asks
for that exact subject. Avoid generic engagement-bait endings such as
"comment below", "like and subscribe", or "what do you think?".
For a blue-sky explanation, end with directly filmable sky, clouds, sunset,
or sunlight footage, never people commenting on the explanation. Use 3–5 scenes for a 25-second video, at most 6 scenes. The system will fail a scene when
exact suitable footage cannot be verified; never weaken the scene to hide that failure.
"""
        from media_first import active_palette, footage_prompt
        palette = active_palette()
        if palette:
            user += "\n\n" + footage_prompt(palette)
        from science_sources import active_evidence, evidence_prompt
        bundle = active_evidence()
        if bundle:
            user += "\n\n" + evidence_prompt(bundle)
        return system, user

    def speak(self, screenplay, work, settings):
        def local_synthesize():
            from local_voice import synthesize
            return synthesize(screenplay.narration, Path(work) / "local-voice", settings)

        return speak_with_free_fallback(
            screenplay, work, settings,
            edge_synthesize=lambda: original_speak(self, screenplay, work, settings),
            local_synthesize=local_synthesize)

    def background(settings, seconds):
        if settings.background_video:
            raise RuntimeError("Unverified background footage is disabled")
        return None

    script.Scene = PlannedScene
    for name in SCENE_FIELDS:
        script.SCENE_SCHEMA["properties"][name] = {"type": "string"}
        if name not in script.SCENE_SCHEMA["required"]:
            script.SCENE_SCHEMA["required"].append(name)
    script.normalize = normalize
    script.build_prompt = build_prompt
    media.Visuals = pipeline.Visuals = StrictVisuals
    media.background_item = pipeline.background_item = background
    render.prepare_segment = strict_prepare_segment
    pipeline.Studio._speak = speak
    tts._edge = strict_edge
    ffmpeg.run = ffmpeg_run
    _INSTALLED = True
