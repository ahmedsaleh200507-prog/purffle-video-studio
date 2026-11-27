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
import subprocess
import threading
from pathlib import Path
import time
from urllib.parse import urlsplit

from media_validation import portrait_crop_allowed
from portrait_layout import plan_portrait, center_enabled, center_filter, validate_center_sample

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
    for key in ("GROQ_API_KEY", "GEMINI_API_KEY", "PURFFLE_REFERENCE_OPUS_B64", "PIXABAY_API_KEY", "PEXELS_API_KEY", "COVERR_API_KEY", "COVER2", "NPS_API_KEY", "VECTEEZY_API_KEY", "EUROPEANA_API_KEY", "GITHUB_TOKEN", "GH_TOKEN", "HF_TOKEN"):
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
        self._rejected_candidates = set()
        self._technical_rejections = {}
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
        from media_validation import SceneSpec, SceneMatcher, reject_offtopic_science_source
        from video_sources import LicenseValidator
        try:
            raw_plan = json.loads(image_prompt)
            data = _scene_data(raw_plan)
            director_contract = raw_plan.get("_visual_contract")
            if director_contract is not None:
                if (not isinstance(director_contract, dict)
                        or data["object"] != director_contract.get("subject")
                        or data["visual_search_query"] not in director_contract.get("queries", [])):
                    raise ValueError("visual_director_invalid_contract: unrelated scene/query")
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
        attempt_deadline = min(scene_start + (150 if os.environ.get("PURFFLE_SHORTS_PORTRAIT_FIRST")=="1" else 75),
                               getattr(self, "_shot_deadline", float("inf")))
        max_candidates = max(1, min(12, int(os.getenv("CANDIDATES_PER_SOURCE", "4"))))
        # #93: the precise "lava entering ocean" shot was filled by a
        # generic Pixabay lava clip before the curated USGS ocean-entry
        # footage was ever considered. Prefer USGS ONLY for that shot;
        # generic volcano shots keep their existing provider order.
        from era_policy import scene_era, footage_allowed
        era = scene_era(data)
        scene["era_policy"] = era
        source_order = list(self.sources)
        from topic_footage import is_lava_ocean_topic
        exact_ocean_entry = (is_lava_ocean_topic(topic) and any(
            word in data["visual_search_query"].casefold()
            for word in ("ocean", "sea", "coast", "entry", "laze")))
        if exact_ocean_entry and "usgs-video" in source_order:
            source_order.remove("usgs-video")
            source_order.insert(0, "usgs-video")
        from footage_search import discover, discover_portrait_first
        from scene_relevance import search_queries
        from geography_policy import scene_requirement, scoped_queries, require_geography
        required_regions = scene_requirement(raw_plan,topic)
        queries = scoped_queries(search_queries(data,director_contract),required_regions)
        scene["required_regions"] = required_regions
        scene["search_queries"] = queries
        # A fair first round prevents the first provider exhausting all aliases
        # and downloads before the next provider gets any opportunity.
        portrait_first = os.environ.get("PURFFLE_SHORTS_PORTRAIT_FIRST","0")=="1"
        deferred=[]
        if portrait_first:
            batches=discover_portrait_first(self.registry,source_order,queries,attempt_deadline,deferred)
        else:
            batches=((src,items,"any",attempt_deadline) for src,items in
                     discover(self.registry,source_order,queries,attempt_deadline))
        if os.environ.get("PURFFLE_VERIFIED_LIBRARY")=="1":
            from itertools import chain
            from verified_library import candidates as library_candidates
            try:
                library_path=Path("media_cache/verified-library/index.json")
                hits=library_candidates(library_path,self.registry,spec,queries,need,source_order)
                scene["verified_library_candidates"]=len(hits)
                library_deadline=min(attempt_deadline,time.monotonic()+20.)
                batches=chain(((item.source,[item],"library_revalidation",library_deadline)
                               for item in hits),batches)
            except Exception as exc:
                scene["verified_library_error"]=type(exc).__name__
        from editorial_pacing import enabled as pacing_enabled
        opening_compare=(idx==0 and pacing_enabled() and isinstance(self.matcher,SceneMatcher))
        def commit_selection(item,source,url_key,digest,actual_digest,path,quality,match,layout,native_scale,license_info,attribution,source_quality,orientation_phase):
            self.credits.add(attribution)
            self.used_hashes.add(actual_digest)
            self._remember(item, url_key, digest)
            if os.environ.get("PURFFLE_VERIFIED_LIBRARY")=="1":
                try:
                    from verified_library import remember as library_remember
                    match["verified_library_saved"]=library_remember(
                        Path("media_cache/verified-library/index.json"),item,spec,source_quality)
                except Exception as exc:
                    match["verified_library_error"]=type(exc).__name__
            # Coverr's MP4 link contains a signed access token tied
            # to the private API key. The renderer already uses the
            # validated local path: discard the token before emitting
            # reports, metadata, logs or artifact ZIPs.
            if source == "coverr-video":
                item.url = license_info["source_page"]
            scene.update({"status": "selected", "source": source, "id": item.id,
                          "director_contract": director_contract,
                          "source_url": item.url, "downloaded_file": str(path),
                          "sha256": actual_digest, "original_sha256": digest, "quality": quality, "match": match,
                          "metadata_text": str(item.text)[:4000],
                          "portrait_layout": layout,
                          "recorded_date": item.extra.get("recorded_date",""),
                          "geography_evidence": item.extra.get("geography_evidence",{}),
                          "orientation_phase": orientation_phase,
                          "source_orientation": ("portrait" if quality["height"]>quality["width"] else
                                                 "landscape" if quality["width"]>quality["height"] else "square"),
                          "download_evidence":item.extra.get("download_evidence",{}),
                          "license": license_info,
                          "crop": {"focus_x": match.get("crop_focus_x", .5),
                                   "effective_source_width": layout["effective_source_width"],
                                   "effective_source_height": layout["effective_source_height"],
                                   "upscaled_after_crop": native_scale>1.0001,
                                   "crop_scale": round(native_scale, 4)}})
            self._save()
            print(f"[SELECTED FOOTAGE] scene={idx+1} provider={source} id={item.id} "
                  f"actual={item.width}x{item.height} visual_score={match.get('visual_score')} "
                  f"license={license_info.get('id')}", flush=True)
            return item

        for source, candidates, orientation_phase, phase_deadline in batches:
            best,best_rank=None,0.
            comparison_deadline=phase_deadline
            extra_attempts=0
            print(f"[SOURCE CHECK] {source}: {len(candidates)} candidates scene={idx+1} phase={orientation_phase}", flush=True)
            ranked = []
            for item in candidates:
                rejection_key = (spec.object, spec.action,
                                 json.dumps(director_contract, sort_keys=True), item.key)
                if rejection_key in self._rejected_candidates:
                    continue
                parts = urlsplit(item.url)
                url_key = parts.netloc.lower() + parts.path
                technical_reason = self._technical_rejections.get(item.key) or self._technical_rejections.get(url_key)
                if technical_reason:
                    scene['rejections'].append({'source': source, 'id': item.id,
                        'reason': technical_reason, 'stage': 'shared_technical_preflight'})
                    continue
                try:
                    if item.kind != "video" or item.key in self.used or url_key in self.used_urls:
                        raise ValueError("non_video_or_duplicate")
                    if item.width > 0 and item.height > 0:
                        if min(item.width, item.height) < 720:
                            raise ValueError(f"Known source below 720 short side: {item.width}x{item.height}")
                        # #96 spent network/disk budget on 1920x1080 sources
                        # which can never fill a 1080x1920 crop within the
                        # existing 1.20x enlargement policy. Use known media
                        # dimensions to avoid downloading provably unusable
                        # renditions; unknown dimensions still require FFprobe.
                        predicted_scale = _native_portrait_scale(
                            {"width": item.width, "height": item.height},
                            getattr(self.s, "width", 720),
                            getattr(self.s, "height", 1280))
                        if (not portrait_crop_allowed(predicted_scale)
                                and not item.extra.get("download_variants")):
                            reason = (
                                "insufficient_native_resolution: provider reports "
                                f"{item.width}x{item.height} which cannot fill "
                                f"{getattr(self.s, 'width', 720)}x{getattr(self.s, 'height', 1280)} "
                                "within native crop policy")
                            self._technical_rejections[item.key] = reason
                            self._technical_rejections[url_key] = reason
                            raise ValueError(reason)
                    if not footage_allowed(source, era, item.text, item.extra.get("recorded_date","")):
                        raise ValueError("historical_era_mismatch: archival footage cannot illustrate this scene")
                    if not LicenseValidator.validate(item.extra.get("license")):
                        raise ValueError("Unverified or incompatible candidate license")
                    license_info = item.extra.get("license") or {}
                    item.extra["geography_evidence"] = require_geography(required_regions,item.text)
                    # Source IDs and source-page slugs can reveal an unrelated
                    # planet even when the provider's short metadata says
                    # 'volcano magma'. The #69 archive clip is one such case.
                    reject_offtopic_science_source(
                        topic, " ".join((
                            str(item.id), str(item.text),
                            str(license_info.get("source_page", "")))))
                    from topic_footage import contradicts_floating_ship
                    if contradicts_floating_ship(
                            topic, " ".join((str(item.text),
                                         str(license_info.get("source_page", ""))))):
                        raise ValueError("offtopic_floating_ship: stock is a wreck, "
                                         "beached or abandoned vessel, not afloat")
                    # #77: "What happens when lava hits the ocean?" must
                    # never use plain ocean/surfer clips as if they showed
                    # molten lava. Check independent provider title/tags/page
                    # BEFORE costly download or accepting CLIP similarity.
                    from topic_footage import is_lava_ocean_topic, lava_subject_in_metadata
                    if is_lava_ocean_topic(topic) and not lava_subject_in_metadata(
                            " ".join((str(item.text),
                                      str(license_info.get("source_page", ""))))):
                        raise ValueError("offtopic_lava_ocean: source has no lava/volcano context")
                    from topic_footage import (is_glowing_ocean_topic,
                                               bioluminescence_visible_in_metadata)
                    if is_glowing_ocean_topic(topic) and not bioluminescence_visible_in_metadata(
                            " ".join((str(item.text),
                                      str(license_info.get("source_page", ""))))):
                        raise ValueError("offtopic_bioluminescence: provider metadata "
                                         "does not establish glowing marine organisms")
                    # #86: the last scene describes an explosive eruption.
                    # A calm cloud-covered mountain is scientifically related
                    # but MUST NOT stand in for the narrated explosion.
                    from topic_footage import (
                        is_sudden_volcano_eruption_topic,
                        explosive_volcano_evidence_in_metadata)
                    if (idx >= 3 and is_sudden_volcano_eruption_topic(topic)
                            and not explosive_volcano_evidence_in_metadata(
                                " ".join((
                                    str(item.text),
                                    str(license_info.get("source_page", "")))))):
                        raise ValueError(
                            "volcano_final_action_mismatch: no provider evidence "
                            "for an active eruption, plume, ash, or molten lava")
                    action_metadata = "explicit_event"
                    if director_contract:
                        from visual_director import metadata_action_candidate
                        action_metadata = metadata_action_candidate(director_contract, " ".join(
                                (str(item.text),
                                 str(license_info.get("source_page", "")))))
                        if action_metadata == "reject":
                            raise ValueError(
                                "visual_director_action_metadata_mismatch: "
                                "provider cannot establish required visible action")
                    if hasattr(self.matcher, "validate_metadata"):
                        score = self.matcher.validate_metadata(spec, item.text)
                    elif hasattr(self.matcher, "metadata_score"):
                        score = self.matcher.metadata_score(spec, item.text)
                        if score < .45:
                            raise ValueError(f"Unrelated metadata (score {score:.3f})")
                    else:
                        score = 0.0  # injected test matchers have no metadata model
                    from scene_relevance import metadata_evidence
                    evidence = metadata_evidence(data, item.text, director_contract)
                    if evidence["contradictions"]:
                        raise ValueError("semantic_contradiction: " + "; ".join(evidence["contradictions"]))
                    evidence["action_metadata"] = action_metadata
                    item.extra["relevance_evidence"] = evidence
                    ranked.append((score, item, url_key))
                except Exception as exc:
                    self._rejected_candidates.add(rejection_key)
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
                scale = _native_portrait_scale({"width":item.width,"height":item.height},
                                              required_width,required_height)
                if scale <= 1:
                    return 0 if item.height >= item.width else 1
                return 2 if scale <= 1.20 else 3

            ranked.sort(key=lambda row: (row[1].extra.get("relevance_evidence",{}).get("action_metadata") == "subject_only_visual_check", crop_rank(row[1]), -row[0], row[1].rank,
                                          -int(row[1].height > row[1].width),
                                          -min(row[1].width, row[1].height)))
            subject_only_attempts = 0
            for score, item, url_key in ranked[:max_candidates]:
                if best is not None:
                    if extra_attempts>=2 or time.monotonic()+20>=comparison_deadline:
                        break
                    if item.key==best["item"].key or url_key==best["url_key"]:
                        continue
                    extra_attempts+=1
                if item.extra.get("relevance_evidence",{}).get("action_metadata") == "subject_only_visual_check":
                    if subject_only_attempts >= 2:
                        continue
                    subject_only_attempts += 1
                rejection_key = (spec.object, spec.action,
                                 json.dumps(director_contract, sort_keys=True), item.key)
                if time.monotonic() >= phase_deadline:
                    scene["rejections"].append({"source": source, "reason": "orientation_phase_budget_exhausted",
                                                "phase":orientation_phase})
                    break
                path, digest = None, None
                try:
                    from media_validation import download_hd_variant
                    required_width = getattr(self.s,"width",720)
                    required_height = getattr(self.s,"height",1280)
                    def layout_for(q):
                        return plan_portrait(q["width"],q["height"],required_width,required_height)
                    center_quality = {}
                    def check_center(path,q):
                        # Check the actual center before accepting a partial
                        # interval; a moving subject outside the crop is not
                        # evidence of a moving opening. Later calm B-roll can
                        # be used only after independent source motion proof.
                        from object_framing import enabled as smart_crop_enabled
                        if center_enabled() and not smart_crop_enabled() and isinstance(self.matcher, SceneMatcher) and q["width"]>=q["height"]:
                            center_quality.clear()
                            center_quality.update(validate_center_sample(path,q,required_width,required_height,
                                self.quality,seconds=min(5.,float(need)),require_motion=(idx==0)))
                    path, source_quality = download_hd_variant(item, self.downloader, self.quality, need=need,
                        segment_seconds=max(1.,float(need)+.5),
                        check=lambda q: layout_for(q) is not None,
                        segment_check=check_center)
                    if source == "coverr-video":
                        # Count a real asset download using Coverr's official
                        # PATCH endpoint, as required on the free API tier.
                        self.registry.track_download(item)
                    if orientation_phase in ("portrait","unknown_orientation") and source_quality["height"]<=source_quality["width"]:
                        # Actual file dimensions (including rotation) override
                        # provider guesses. Do not count a deferred landscape as
                        # a rejection or delete its cached original.
                        deferred.append((source,item))
                        continue
                    digest = self.downloader.digest(path)
                    if digest in self.used_hashes or (best is not None and digest in (best["digest"],best["actual_digest"])):
                        raise ValueError("duplicate content hash")
                    # Source durations are measured by FFprobe. A 10.060s
                    # genuine clip covers a 10.000s narration scene; the old
                    # arbitrary +0.100s margin wrongly discarded it.
                    # Requiring the ACTUAL scene duration still forbids
                    # looping, frozen tail frames or insufficient footage.
                    quality = source_quality
                    # Search later source intervals only for a required visible
                    # event. Keep original digest for source deduplication.
                    window_review = {"state":"disabled","offset":0.}
                    if (os.environ.get("PURFFLE_ACTION_WINDOW")=="1"
                            and isinstance(self.matcher,SceneMatcher)
                            and director_contract and director_contract.get("event_required")):
                        from action_window import select_window,extract_window
                        window_review=select_window(path,float(quality["duration"]),float(need),
                            director_contract,scorer=self.matcher._similarities,deadline=phase_deadline,
                            opening=(idx==0))
                        if window_review["offset"]>0:
                            trimmed=None
                            try:
                                trimmed=extract_window(path,window_review["offset"],float(need),deadline=phase_deadline)
                                trimmed_quality=self.quality.validate(trimmed,need=need)
                                if layout_for(trimmed_quality) is None:
                                    raise ValueError("Trim cannot satisfy output dimensions")
                                trimmed_digest=self.downloader.digest(trimmed)
                                window_review["state"]="materialized_pending_full_validation"
                                window_review["original_sha256"]=digest
                                window_review["trim_sha256"]=trimmed_digest
                                path=trimmed
                                quality=trimmed_quality
                            except Exception as exc:
                                if trimmed is not None:
                                    trimmed.unlink(missing_ok=True)
                                window_review.update(state="trim_failed_keep_original",error_type=type(exc).__name__,offset=0.)
                    layout = layout_for(quality)
                    if layout is None:
                        raise ValueError("No valid portrait layout for measured source")
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
                        # Measured resolution cannot improve for another spoken
                        # scene. Do not delete then redownload the same huge file.
                        reason = (f'insufficient_native_resolution: measured {quality["width"]}x'
                                  f'{quality["height"]} cannot fill {required_width}x{required_height} within crop limit')
                        self._technical_rejections[item.key] = reason
                        self._technical_rejections[url_key] = reason
                        raise ValueError(
                            "insufficient_native_resolution: 9:16 crop would upscale beyond safe limit "
                            f"{quality.get('width')}x{quality.get('height')} source "
                            f"to {required_width}x{required_height}"
                        )
                    match = self.matcher.match(path, spec, metadata=item.text, duration=need)
                    match["action_window"]=window_review
                    if center_enabled():
                        match["crop_focus_x"] = .5
                    from object_framing import enabled as smart_crop_enabled,propose
                    if smart_crop_enabled() and isinstance(self.matcher,SceneMatcher):
                        subject=" ".join(x for x in (spec.main_character,spec.object) if x)
                        framing=propose(path,float(need),subject,quality["width"],quality["height"],
                                        required_width,required_height,float(match.get("crop_focus_x",.5)),deadline=phase_deadline)
                        match["object_framing"]=framing
                        if framing["state"]=="proposed":
                            match["crop_focus_x"]=framing["focus_x"]
                            layout={**layout,"mode":"object_guided_crop"}
                        # Verify movement and native resolution in the exact
                        # chosen crop, not the old centered preview.
                        if quality["width"]>=quality["height"]:
                            center_quality=validate_center_sample(path,quality,required_width,required_height,
                                self.quality,seconds=min(5.,float(need)),require_motion=(idx==0),
                                focus=float(match["crop_focus_x"]))
                    quality["portrait_layout"] = layout
                    if center_quality:
                        quality["center_crop_motion_mode"]=center_quality["motion_mode"]
                        quality["center_crop_motion_score"]=center_quality["motion_score"]
                    item.extra["portrait_layout"] = layout
                    # #106: an octopus stock clip passed whole-frame motion
                    # and CLIP but half of the final 9:16 render was black.
                    # Sample the actual portrait crop before accepting it.
                    # Ordinary dark storm footage with detail on both sides
                    # is not penalized as a pillarbox.
                    if isinstance(self.matcher, SceneMatcher):
                        from opening_impact import _first_frames
                        from visual_crop_integrity import assess_portrait_pillarbox
                        crop_focus = float(match.get("crop_focus_x", .5))
                        seconds = min(float(quality["duration"]), float(need))
                        check_times = (.15, max(.2, seconds*.45),
                                       max(.3, min(seconds*.85, seconds-.25)))
                        crop_frames = _first_frames(
                            path, focus=crop_focus, seconds=check_times)
                        crop_integrity = assess_portrait_pillarbox(crop_frames)
                        if not crop_integrity["verified"]:
                            raise ValueError(
                                "portrait_pillarbox_invalid: " +
                                crop_integrity["reason"])
                        match["portrait_integrity"] = crop_integrity
                        from crop_subject_policy import verify_crop_subject
                        from source_overlay import check_source
                        match["source_overlay"]=check_source(path,float(need),crop_focus)
                        match["crop_subject_proof"]=verify_crop_subject(crop_frames,spec,self.matcher)
                        # Production #103: the second whale shot passed CLIP but
                        # independent SigLIP favored alternatives in two frames.
                        # Reject this measured disagreement for whale candidates,
                        # not missing/disabled optional inference.
                        from topic_footage import words
                        second=match["crop_subject_proof"].get("siglip_shadow_review",{})
                        if (words(spec.object) & {"whale","wal","wale","buckelwal"}
                                and second.get("state")=="observed"
                                and second.get("agrees") is False):
                            raise ValueError("whale_subject_secondary_disagreement: SigLIP did not corroborate the visible whale")
                    from scene_relevance import suitability
                    match["suitability"] = suitability(item.extra.get("relevance_evidence", {}), match, quality)
                    # #84: A generic 'ship outdoors' CLIP score let a mostly
                    # empty sea scene through. Compare the actual first 1.2 s
                    # of the *vertical crop* with subject-vs-empty-scenery,
                    # for every scene, BEFORE it is committed to the renderer.
                    # This complements (not replaces) existing licenses,
                    # clip-level CLIP, motion, source provenance and dedup.
                    from topic_footage import opening_subject_prompts
                    from media_validation import SceneMatcher
                    subject_specification = opening_subject_prompts(topic)
                    if idx >= 3 and is_sudden_volcano_eruption_topic(topic):
                        from topic_footage import explosive_volcano_last_shot_prompts
                        subject_specification = explosive_volcano_last_shot_prompts()
                    if subject_specification and isinstance(self.matcher, SceneMatcher):
                        from opening_impact import _first_frames, _semantic_subject_screen
                        focus = float(match.get("crop_focus_x", .5))
                        # The hook uses its actual first second; later
                        # narrated scenes must also show the topic subject
                        # around the middle, not only an unrelated transition.
                        # #92's bathroom mirror clip showed PALMS in scene 2.
                        if idx == 0:
                            cropped_frames = _first_frames(path, focus=focus)
                        else:
                            mid = max(1.15, min(float(need) * .6,
                                                float(quality["duration"]) * .7))
                            near_end = max(mid + .05, min(
                                float(need) * .88,
                                float(quality["duration"]) - .30))
                            cropped_frames = _first_frames(
                                path, focus=focus,
                                seconds=(.15, mid, near_end))
                        # Stop approving faint CLIP preferences for storm
                        # clouds, empty sea or small background ships. A
                        # physical object must remain visible in the scene;
                        # lightning is brief so it needs stronger contrast
                        # but NOT persistent flashes in every sampled frame.
                        subject_kind = subject_specification["subject"]
                        permanent_subject = subject_kind in {
                            "bathroom_mirror", "iceberg",
                            "floating_cargo_ship"}
                        critical_margin = (.05 if subject_kind == "lightning"
                            else .032 if permanent_subject else .012)
                        subject_result = _semantic_subject_screen(
                            cropped_frames, subject_specification,
                            scorer=self.matcher._similarities,
                            require_all_frames=permanent_subject,
                            minimum_margin=critical_margin)
                        if not subject_result["verified"]:
                            raise ValueError(
                                "visual_subject_not_grounded: vertical scene "
                                "shows scenery rather than the main topic subject")
                        match["subject_screen"] = subject_result
                    if director_contract and isinstance(self.matcher, SceneMatcher):
                        from visual_director import verify_visible_event_or_illustrative_subject
                        event_check = verify_visible_event_or_illustrative_subject(
                            path, min(float(need), float(quality["duration"])),
                            match.get("crop_focus_x", .5),
                            director_contract, match,
                            scorer=self.matcher._similarities,
                            opening=(idx == 0))
                        match["director_check"] = event_check
                    # Dynamic materialization is optional and never replaces a
                    # validated static clip until the derived clip passes again.
                    dynamic_review={"state":"not_applied"}
                    track=match.get("object_framing",{}).get("tracking_shadow",{})
                    if (os.environ.get("PURFFLE_DYNAMIC_CROP")=="1"
                            and track.get("state")=="shadow_proposal"
                            and native_scale<=1.0001 and isinstance(self.matcher,SceneMatcher)):
                        from dynamic_crop import render_tracked
                        derived=None
                        try:
                            derived=render_tracked(path,track,float(need),required_width,required_height,
                                                   deadline=phase_deadline)
                            q2=self.quality.validate(derived,need=float(need)+.05)
                            if (q2["width"],q2["height"])!=(required_width,required_height):
                                raise ValueError("Dynamic crop dimensions mismatch")
                            m2=self.matcher.match(derived,spec,metadata=item.text,duration=need)
                            m2["crop_focus_x"]=.5
                            frames2=_first_frames(derived,focus=.5,seconds=check_times)
                            integrity2=assess_portrait_pillarbox(frames2)
                            if not integrity2["verified"]:
                                raise ValueError("Dynamic crop border check failed")
                            m2["source_overlay"]=check_source(derived,float(need),.5)
                            proof2=verify_crop_subject(frames2,spec,self.matcher)
                            second2=proof2.get("siglip_shadow_review",{})
                            if second2.get("state")=="observed" and second2.get("agrees") is False:
                                raise ValueError("Dynamic crop secondary disagreement")
                            if subject_specification:
                                check2=_semantic_subject_screen(frames2,subject_specification,
                                    scorer=self.matcher._similarities,
                                    require_all_frames=permanent_subject,minimum_margin=critical_margin)
                                if not check2["verified"]:
                                    raise ValueError("Dynamic crop topic mismatch")
                                m2["subject_screen"]=check2
                            if director_contract:
                                m2["director_check"]=verify_visible_event_or_illustrative_subject(
                                    derived,float(need),.5,director_contract,m2,
                                    scorer=self.matcher._similarities,opening=(idx==0))
                            if idx==0:
                                from opening_impact import _evaluate_frames
                                if not _evaluate_frames(_first_frames(derived,focus=.5)).get("verified"):
                                    raise ValueError("Dynamic opening failed")
                            derived_digest=self.downloader.digest(derived)
                            layout2=layout_for(q2)
                            if layout2 is None:
                                raise ValueError("Dynamic layout unavailable")
                            dynamic_review={"state":"validated_materialized","keyframes":track["keyframes"],
                                "source_dimensions":[quality["width"],quality["height"]],
                                "source_sha256":digest,"derived_sha256":derived_digest,
                                "sampled_box_coverage":track["tracked_coverage"]}
                            m2.update(object_framing=match.get("object_framing",{}),
                                action_window=window_review,portrait_integrity=integrity2,
                                crop_subject_proof=proof2,
                                suitability=suitability(item.extra.get("relevance_evidence",{}),m2,q2))
                            q2["original_source_quality"]=quality
                            layout2={**layout2,"mode":"dynamic_materialized_crop"}
                            q2["portrait_layout"]=layout2
                            path,quality,match,layout=derived,q2,m2,layout2
                            item.extra["portrait_layout"]=layout2
                        except Exception as exc:
                            if derived is not None:
                                derived.unlink(missing_ok=True)
                            dynamic_review={"state":"static_fallback","error_type":type(exc).__name__}
                    match["dynamic_crop"]=dynamic_review
                    if (os.environ.get("PURFFLE_EVENT_THEME_REVIEW")=="1"
                            and isinstance(self.matcher,SceneMatcher)):
                        try:
                            from event_theme_review import observe_theme
                            final_frames=frames2 if dynamic_review["state"]=="validated_materialized" else crop_frames
                            match["theme_review"]=observe_theme(final_frames,topic,spec.object,subject_specification)
                        except Exception as exc:
                            match["theme_review"]={"state":"unavailable","error_type":type(exc).__name__}
                    from visual_consensus import summarize as summarize_visual_evidence
                    match["visual_consensus"]=summarize_visual_evidence(match)
                    if window_review["state"]=="materialized_pending_full_validation":
                        window_review["state"]="validated_interval"
                    item.path = path
                    item.width, item.height = int(quality["width"]), int(quality["height"])
                    item.duration = float(quality["duration"])
                    actual_digest=self.downloader.digest(path)
                    item.extra.update({"quality": quality, "match": match, "start": 0.0,
                                       "strict_validated": True, "sha256": actual_digest,
                                       "original_sha256": digest})
                    license_info = item.extra.get("license", {})
                    # #91 lava failure: selecting the first on-topic 4K clip
                    # and checking the opening only AFTER all three scenes
                    # wasted the whole production. Reject dark/late-action
                    # intros here, then try the next genuine moving clip.
                    # Use the exact same scoring/semantic/lava gate as the
                    # final preflight; never lower the editorial threshold.
                    if idx == 0 and isinstance(self.matcher, SceneMatcher):
                        from opening_impact import prioritize_opening
                        opening_candidate = prioritize_opening(
                            topic, [item], [data], [{
                                "match": match,
                                "license": license_info,
                                "source_url": item.url,
                            }])
                        match["opening_preflight"] = {
                            "state": opening_candidate["state"],
                            "chosen_score": opening_candidate["chosen_score"],
                        }
                    attribution = license_info.get("attribution") or item.credit
                    if not attribution:
                        raise ValueError("Missing license provenance/attribution")
                    candidate=dict(item=item,source=source,url_key=url_key,digest=digest,
                        actual_digest=actual_digest,path=path,quality=quality,match=match,layout=layout,
                        native_scale=native_scale,license_info=license_info,attribution=attribution,
                        source_quality=source_quality,orientation_phase=orientation_phase)
                    if opening_compare:
                        from editorial_pacing import better_opening
                        rank=float(match["opening_preflight"]["chosen_score"])
                        if best is None or better_opening(rank,best_rank):
                            best,best_rank=candidate,rank
                        if best_rank>=90 or extra_attempts>=2 or time.monotonic()+20>=comparison_deadline:
                            break
                        if comparison_deadline==phase_deadline:
                            comparison_deadline=min(phase_deadline,time.monotonic()+35)
                        continue
                    return commit_selection(**candidate)
                except Exception as exc:
                    self._rejected_candidates.add((spec.object, spec.action,
                        json.dumps(director_contract, sort_keys=True), item.key))
                    # A rejected 4K file must not accumulate until it fills the CI disk.
                    # Preserve anything referenced by accepted footage, including a
                    # duplicate hash reached through another URL.
                    if (path is not None and digest is not None and digest not in self.used_hashes
                            and (best is None or (digest not in (best["digest"],best["actual_digest"])
                                 and Path(path)!=Path(best["path"])))):
                        try:
                            Path(path).unlink(missing_ok=True)
                            Path(path).with_suffix(".json").unlink(missing_ok=True)
                        except OSError:
                            pass  # aggregate cache budget still fails safely when full
                    reason = _redact(f"{type(exc).__name__}: {exc}")[:450]
                    scene["rejections"].append({"source": source, "id": item.id,
                                                "reason": reason, "stage": "download_quality_or_visual"})
                    print(f"[REJECTED FOOTAGE] scene={idx+1} provider={source} id={item.id} reason={reason}", flush=True)
            if best is not None:
                best["match"]["opening_comparison"]={"state":"best_verified_in_bounded_batch","chosen_score":best_rank,"extra_attempts":extra_attempts,"scope":"editorial heuristic; not a views prediction"}
                return commit_selection(**best)
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
    layout=item.extra.get("portrait_layout",{})
    item.extra["crop"] = {"focus_x": focus, "effective_source_width": round(crop_width),
                          "effective_source_height": round(crop_height),
                          "upscaled_after_crop": layout.get("foreground_scale",measured_scale)>1.0001,
                          "crop_scale": round(measured_scale, 4),
                          "layout_mode":layout.get("mode","subject_crop")}
    # Keep the subject's horizontal focus; vertically centre when a wide crop is required.
    cover = (f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,"
             f"crop={W}:{H}:x='max(0,min(iw-ow,iw*{focus:.5f}-ow/2))':y='(ih-oh)/2',setsar=1")
    # The exact accepted focus must survive rendering, including recovery.
    from portrait_layout import focus_filter
    cover=focus_filter(W,H,focus)
    out = Path(work) / f"seg{idx:02d}.mp4"
    ffmpeg.run(["-threads", "2", "-filter_threads", "1", "-ss", "0", "-i", str(item.path),
                "-t", f"{seconds:.3f}", "-an", "-vf", f"{cover},fps={F}{_grade(settings)}",
                *_encode_args(settings, final=False), "-threads", "2", "-frames:v", str(max(2, round(seconds*F))), str(out)],
               label=f"validated segment {idx}", timeout=240)
    from editorial_pacing import enabled as pacing_enabled
    if pacing_enabled():
        try:
            measured=subprocess.run(["ffprobe","-v","error","-show_entries","format=duration",
                "-of","default=noprint_wrappers=1:nokey=1",str(out)],
                capture_output=True,text=True,check=True,timeout=10)
            measured_seconds=float(measured.stdout.strip())
            if math.isfinite(measured_seconds) and measured_seconds>0:
                item.extra["editorial_segment_seconds"]=measured_seconds
        except (OSError,ValueError,subprocess.SubprocessError):
            item.extra["editorial_segment_seconds"]=None
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
    timeout_seconds = max(1, min(600 if stage == "Approved private reference narrator" else 180,
                                 float(timeout_seconds)))
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
        # Exactly the two requested, pinned Piper identities are accepted.
        approved = {"en": ("en_US-joe-medium", "CC0"),
                    "de": ("de_DE-thorsten-medium", "CC0-1.0")}
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
    """Synthesize only the fixed Piper identity; failures never switch voices."""
    from english_reference_policy import enforce_english_reference_only
    enforce_english_reference_only(settings.language)
    if settings.offline or settings.tts_engine not in ("edge", "piper") or settings.language not in ("de", "en"):
        raise RuntimeError("Strict production requires free Edge/local narration in de/en")
    male_lock = True
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
    # V4 has one fixed voice per language, irrespective of legacy env flags.
    engines = (("piper", local_synthesize, "Locked male Piper narrator"),)
    for engine, synthesize, stage in engines:
        started = time.monotonic()
        try:
            timeout = os.getenv("EDGE_TTS_TIMEOUT_SECONDS", "180") if engine == "edge" else 180
            speech = with_voice_deadline(synthesize, timeout_seconds=timeout, stage=stage)
            _validate_free_speech(speech, engine, settings.language)
            if screenplay is not None:
                from purffle_shorts.timing import tokenize
                expected_tokens = tokenize(screenplay.narration, settings.language)
                if [w.text for w in speech.words] != expected_tokens:
                    raise RuntimeError("Narration caption tokens differ from the complete script")
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
    raise RuntimeError("Locked male narrator unavailable; refusing to substitute a female or different voice")


def install():
    global _INSTALLED
    if _INSTALLED:
        return
    verify_upstream()
    import purffle_shorts.script as script
    import purffle_shorts.llm as upstream_llm
    from local_llm import install_short_provider
    install_short_provider(upstream_llm)
    from cloud_model_router import install_short_provider as install_cloud_router
    install_cloud_router(upstream_llm)
    # The pinned upstream still defaults to the older Gemini 2.5 Flash
    # family. Select a documented free-tier text model ONLY for Gemini,
    # leaving existing Groq model, narrator and Shorts scene rules intact.
    from dataclasses import replace as dataclass_replace
    upstream_llm.PRESETS["gemini"] = dataclass_replace(
        upstream_llm.PRESETS["gemini"],
        default_model="gemini-3.1-flash-lite")
    # Preserve the original user-tested Groq GPT-OSS model when it serves
    # as the SECOND provider. Upstream's generic fallback Llama model is
    # different and would silently change voice/text quality.
    upstream_llm.PRESETS["groq"] = dataclass_replace(
        upstream_llm.PRESETS["groq"],
        default_model="openai/gpt-oss-20b")
    import purffle_shorts.media as media
    import purffle_shorts.render as render
    import purffle_shorts.pipeline as pipeline
    import purffle_shorts.ffmpeg as ffmpeg
    import purffle_shorts.tts as tts
    import purffle_shorts.overlays as overlays
    from attention_hook import install_attention_hook, kinetic_hook_filter

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
        # Add a gentle 0.4s spring entrance only to the intro hook;
        # keep video, audio and word-level captions unchanged.
        return original_ffmpeg_run(bounded_ffmpeg_args(kinetic_hook_filter(args)), **kwargs)

    def normalize(data, subject, style, language):
        from fact_checked_topics import ground_lightning_explainer
        # Generic LLM rules alone did not prevent #70 inventing an Elm Street
        # oak tree hit 12 times and an unreferenced 300,000-volt measurement.
        # For this well-defined educational topic use a NOAA-grounded concise
        # script with shootable B-roll rather than publish a fictional event.
        from media_first import active_palette, align_script_to_palette
        palette = active_palette()
        from visual_director import story_scene_target
        requested_scene_count = (
            len(palette.plans) if palette else story_scene_target())
        data = ground_lightning_explainer(
            data, subject, language,
            scene_count=requested_scene_count)
        from fact_checked_topics import ground_verified_documentary
        data = ground_verified_documentary(
            data, subject, language,
            scene_count=requested_scene_count)
        # The verified video palette is authoritative for visual planning.
        # Narration may explain abstract facts without requiring exact footage.
        data = align_script_to_palette(data, palette)
        raw_scenes = data.get("scenes") or []
        if not raw_scenes or len(raw_scenes) > 6:
            raise ValueError("A strict video needs 1–6 explicit scenes")
        prepared, plans = [], []
        from visual_director import anchor_observational_science_scene
        for raw in raw_scenes:
            raw = anchor_observational_science_scene(raw, subject)
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
time, visual_search_query. These values are ALWAYS English.
CRITICAL OUTPUT SCHEMA: Do NOT omit 'action' or any of these six fields.
For a filmed subject that has no specific activity, use action='ambient'
as a STRING, rather than omitting the field; object and English
visual_search_query MUST remain concrete and searchable. Every narration
line must have a complete associated plan, and any missing key will be
rejected and cause a full redraft. Do not invent a visible event to fill a key.
When sources are encyclopedia excerpts, avoid unsourced percentages,
numbers, dates and exact measurements. Only state claims supported by the
independent extracts, without adding unsupported detail. Use empty main_character if
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
AUDIENCE RETENTION STORYBOARD — for accurate educational Shorts:
- SCENE 1 (first ~2 seconds of speech): Start with the strongest REAL, visually
  filmable observation from the requested topic, in a vivid concise sentence.
  Do not start with "Hello", "Welcome", "Did you know", "In this video",
  "Today we will learn", a channel introduction, or an unrelated setup.
  Make a specific curiosity gap without fabricating danger, records or discoveries.
- SCENE 2: Deliver a first meaningful answer or fact IMMEDIATELY. Never
  artificially withhold all explanation until the end.
- MIDDLE SCENES: Each scene must add a DIFFERENT fact, consequence, contrast
  or mechanism that advances the explanation. Do not rephrase the hook over
  several shots, repeat generic suspense, or pad with rhetorical questions.
- FINAL SCENE: Give the clear factual payoff and a satisfying visual conclusion
  directly tied to the subject. No like/subscribe/comment CTA and no invented cliffhanger.
- Use natural spoken English or German with short sentences. Let scenes shift
  with the VERIFIED moving footage; never say an unrelated clip depicts
  an event that is not actually shown. Captions will follow exactly spoken words.
- Do not recite the entire title: oversized on-screen title cards are disabled.
  The hook is the actual first moving footage plus your concise spoken line,
  supported by synchronized word captions. Prefer specific nouns and active verbs; keep each
  narration line within the verified shot's time limit.
- This is an editorial pacing guideline, NOT permission to exaggerate or
  override any of the independent source, license, safety or accuracy checks.
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
or sunlight footage, never people commenting on the explanation. Length is FLEXIBLE based on the topic, available verified footage and real facts: do not force 30 seconds, pad narration or loop clips. FIRST 1–2 SECONDS: immediate compelling real moving subject with a short truthful spoken hook (NO giant title overlay). Then move through curiosity, development with fresh facts, and a complete truthful payoff. Keep the opening short regardless of the video length. The system will fail a scene when
exact suitable footage cannot be verified; never weaken the scene to hide that failure.
"""
        from visual_director import story_scene_target
        target_scenes = story_scene_target()
        if target_scenes is not None:
            user += (
                f"\\nSOURCE-REVIEWED STORY FIRST: Write exactly {target_scenes} "
                "complete, short factual scenes. Do not stretch a story to "
                "four shots. The renderer will look for independently "
                "verified real video for EACH spoken scene, in this order.")
        from visual_director import footage_feedback
        feedback = footage_feedback()
        if feedback:
            user += (
                "\n\nREAL-FOOTAGE RECOVERY (ONE bounded revision): "
                "The following earlier scene searches found no licensed, "
                "visually verified footage. Keep the same factual topic, "
                "language and complete source-supported explanation, but "
                "choose DIFFERENT common, directly filmable visible actions "
                "for these scene slots. Do not claim a literal event is "
                "visible when only illustrative B-roll exists. Never invent "
                "a fact, silently omit the answer, or use generic filler. "
                "Do not repeat the unavailable search queries.\n"
                + feedback)
        from media_first import active_palette, footage_prompt
        palette = active_palette()
        if palette:
            user += "\n\n" + footage_prompt(palette)
        from science_sources import active_evidence, evidence_prompt, review_feedback
        source_feedback = review_feedback()
        if source_feedback:
            user += (
                "\n\nSOURCE-REVIEW REDRAFT (ONE bounded revision): The previous "
                "draft contained the unsupported claim(s) below. Never repeat "
                "those claims unless a supplied independent source excerpt "
                "explicitly supports them. Replace them with different, "
                "simple, source-supported scientific facts, keep the full "
                "answer to the requested topic, and do not invent new "
                "measurements, experiments or causal claims.\n"
                + source_feedback)
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
    install_attention_hook(overlays)
    from short_caption_style import install_style
    install_style(overlays)
    pipeline.Studio._speak = speak
    tts._edge = strict_edge
    ffmpeg.run = ffmpeg_run
    _INSTALLED = True
