"""Bounded media download, measured source quality and local visual verification.

No image generation or paid inference is used. CLIP scores are screening evidence,
not proof of character identity, actions, or factual accuracy.
"""
from __future__ import annotations

import hashlib
import io
import ipaddress
import json
import math
import os
import re
import shutil
import socket
import statistics
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path


_CONTAINERS = "mov,mp4,m4a,3gp,3g2,mj2,matroska,webm,ogg,mpegts,mpeg,avi"
_INPUT_GUARDS = ["-protocol_whitelist", "file,pipe", "-format_whitelist", _CONTAINERS]


def portrait_crop_limit() -> float:
    # Explicit user-selected centered fullscreen fallback: a 720p source
    # may need 1920/720 enlargement. Strict callers keep the original bound.
    import os
    if os.environ.get("PURFFLE_SHORTS_CENTER_CROP") == "1":
        return 8/3
    """Single shared bound for selecting, rendering and accepting footage.

    A genuine 1080p landscape clip needs about 1.1852x to fill 720x1280
    after the 9:16 crop. This never allows an arbitrarily upscaled 720p
    landscape source to masquerade as HD. Native resolution is still reported.
    """
    value = float(os.environ.get("PURFFLE_MAX_PORTRAIT_UPSCALE", "1.20"))
    if not math.isfinite(value):
        raise ValueError("PURFFLE_MAX_PORTRAIT_UPSCALE must be finite")
    return min(1.20, max(1.0, value))




def portrait_crop_allowed(scale: float) -> bool:
    """Require all three footage gates to use the same numeric policy."""
    scale = float(scale)
    return math.isfinite(scale) and scale > 0 and scale <= portrait_crop_limit() + 0.0001


def reject_offtopic_science_source(topic: str, candidate_text: str) -> None:
    """Block known, provable domain contradictions before downloading footage.

    Topic-related B-roll can be illustrative, but Earth's volcanic eruptions
    must not show a clip about cryovolcanoes on Pluto/Mars/etc as if it were
    footage of an Earth magma chamber. Search titles and provider identifiers
    may be concatenated (e.g. 'PlutoInAMinute...'), so match compact text.
    This deliberately doesn't infer identity from images or drop generic B-roll.
    """
    subject = str(topic or "").casefold()
    if not any(word in subject for word in ("volcano", "volcan", "eruption", "erupt", "magma", "lava")):
        return
    source = re.sub(r"[^a-z]", "", str(candidate_text or "").casefold())
    topic_compact = re.sub(r"[^a-z]", "", subject)
    # Only explicit off-world mentions are disqualifying. A NASA/space-provider
    # label alone is not proof that a volcano video is off-topic.
    planetary_bodies = ("pluto", "mars", "venus", "enceladus", "triton",
                        "europa", "titan", "mercury", "neptune")
    other_world = next((world for world in planetary_bodies
                        if world in source and world not in topic_compact), None)
    if other_world:
        raise ValidationError(
            f"Off-topic planetary volcanic footage: source depicts {other_world}, "
            "not the subject of the narration")


class ValidationError(RuntimeError):
    """A candidate cannot be accepted; callers must try another or fail the scene."""


@dataclass(frozen=True)
class SceneSpec:
    main_character: str = ""
    object: str = ""
    action: str = ""
    location: str = ""
    time: str = ""
    visual_search_query: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "SceneSpec":
        if not isinstance(data, dict):
            raise ValidationError("Scene specification must be an object")
        fields = {k: str(data.get(k) or "").strip() for k in cls.__dataclass_fields__}
        fields["main_character"] = fields["main_character"] or str(data.get("character") or "")
        fields["visual_search_query"] = fields["visual_search_query"] or str(data.get("search_query") or "")
        spec = cls(**fields)
        if not spec.visual_search_query or not spec.object or not spec.action:
            raise ValidationError("Scene requires object, action and visual_search_query")
        return spec

    def to_dict(self) -> dict:
        return asdict(self)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class VideoDownloader:
    """HTTPS only; validate every redirect, bound bytes/time, atomically cache files."""
    _cache_lock = threading.RLock()

    def __init__(self, cache_dir=Path("media_cache/downloads"), *, max_bytes=350 * 1024 * 1024,
                 max_cache_bytes=2 * 1024 ** 3, min_free_bytes=1024 ** 3,
                 timeout=25, total_timeout=180, opener=None):
        self.cache_dir = Path(cache_dir)
        self.max_bytes = max_bytes
        self.max_cache_bytes = max_cache_bytes
        self.min_free_bytes = min_free_bytes
        self.timeout = timeout
        self.total_timeout = total_timeout
        self.opener = opener or urllib.request.build_opener(_NoRedirect())
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def validate_url(url: str) -> None:
        try:
            parsed = urllib.parse.urlsplit(url)
            port = parsed.port
        except ValueError as exc:
            raise ValidationError("Malformed video URL") from exc
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or port not in (None, 443)):
            raise ValidationError("Download requires a public HTTPS URL without credentials")
        try:
            records = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
        except OSError as exc:
            raise ValidationError("Download host cannot be resolved") from exc
        if not records or any(not ipaddress.ip_address(r[4][0].split("%")[0]).is_global for r in records):
            raise ValidationError("Private, loopback, link-local and reserved download hosts are forbidden")

    @staticmethod
    def digest(path: Path) -> str:
        h = hashlib.sha256()
        with Path(path).open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()

    def download(self, url: str) -> Path:
        with self._cache_lock:
            return self._download(url)

    def _download(self, url: str) -> Path:
        self.validate_url(url)
        key = hashlib.sha256(url.encode()).hexdigest()
        target = self.cache_dir / (key + ".bin")
        # The cache has no unverified shortcut: a sidecar authenticates content,
        # and the quality validator still probes cached media on every selection.
        sidecar = target.with_suffix(".json")
        if target.is_file() and sidecar.is_file():
            try:
                saved = json.loads(sidecar.read_text())
                if (0 < target.stat().st_size <= self.max_bytes
                        and saved["sha256"] == self.digest(target)):
                    target.touch()
                    return target
            except (ValueError, KeyError, OSError):
                pass
        # Never evict files that the renderer may still hold. Expire only files
        # from runs older than one day, and refuse before exhausting disk.
        for old in self.cache_dir.glob("*.bin"):
            if time.time() - old.stat().st_mtime > 86400:
                old.unlink(missing_ok=True)
                old.with_suffix(".json").unlink(missing_ok=True)
        cache_bytes = sum(f.stat().st_size for f in self.cache_dir.iterdir() if f.is_file())
        if cache_bytes + self.max_bytes > self.max_cache_bytes:
            raise ValidationError("Download cache byte budget exhausted")
        if shutil.disk_usage(self.cache_dir).free < self.min_free_bytes + self.max_bytes:
            raise ValidationError("Insufficient free disk for bounded video download")
        started = time.monotonic()
        current = url
        response = None
        for _ in range(6):
            self.validate_url(current)
            if time.monotonic() - started > self.total_timeout:
                raise ValidationError("Download time budget exceeded")
            # Asset manifests (notably NASA) can contain spaces or Unicode
            # paths. Encode those while retaining existing signed escapes.
            parts = urllib.parse.urlsplit(current)
            current = urllib.parse.urlunsplit((parts.scheme, parts.netloc,
                urllib.parse.quote(parts.path, safe="/%:@!$&'()*+,;=-._~"),
                urllib.parse.quote(parts.query, safe="=&%/?+,:;@!$'()*~-._"), ""))
            req = urllib.request.Request(current, headers={
                "User-Agent": "PurffleVideoStudio/2.0 (+https://github.com/ahmedsaleh200507-prog/purffle-video-studio)",
                "Accept": "video/*,application/octet-stream;q=0.8", "Accept-Encoding": "identity"})
            try:
                response = self.opener.open(req, timeout=self.timeout)
                break
            except urllib.error.HTTPError as exc:
                if exc.code in (301, 302, 303, 307, 308):
                    location = exc.headers.get("Location")
                    exc.close()
                    if not location:
                        raise ValidationError("Redirect has no destination") from exc
                    current = urllib.parse.urljoin(current, location)
                    continue
                raise ValidationError(f"Video download HTTP {exc.code}") from exc
            except (OSError, urllib.error.URLError) as exc:
                raise ValidationError("Video download transport failure") from exc
        if response is None:
            raise ValidationError("Too many download redirects")
        temp_path = None
        try:
            with response:
                self.validate_url(response.geturl())
                content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
                if content_type.startswith(("image/", "text/")) or content_type in ("application/json", "application/xml"):
                    raise ValidationError("Download is not a video response")
                length = response.headers.get("Content-Length")
                try:
                    length = int(length) if length is not None else None
                except ValueError as exc:
                    raise ValidationError("Invalid video Content-Length") from exc
                if length is not None and length < 0:
                    raise ValidationError("Invalid video Content-Length")
                if length and length > self.max_bytes:
                    raise ValidationError("Video exceeds byte budget")
                fd, filename = tempfile.mkstemp(dir=self.cache_dir, suffix=".part")
                temp_path = Path(filename)
                count = 0
                digest = hashlib.sha256()
                with os.fdopen(fd, "wb") as stream:
                    while True:
                        if time.monotonic() - started > self.total_timeout:
                            raise ValidationError("Download time budget exceeded")
                        chunk = response.read(min(1024 * 1024, self.max_bytes - count + 1))
                        if not chunk:
                            break
                        count += len(chunk)
                        if count > self.max_bytes:
                            raise ValidationError("Video exceeds byte budget")
                        stream.write(chunk)
                        digest.update(chunk)
                if count < 1024 or (length and count != length):
                    raise ValidationError("Empty or incomplete video download")
                temp_path.replace(target)
                sidecar.write_text(json.dumps({"sha256": digest.hexdigest(), "bytes": count}))
                return target
        finally:
            if temp_path:
                temp_path.unlink(missing_ok=True)


def _run(cmd: list[str], timeout=30, *, raw=False):
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=timeout, check=True)
    except (subprocess.SubprocessError, OSError) as exc:
        raise ValidationError(f"Media command failed: {cmd[0]}") from exc
    return result.stdout if raw else result.stdout.decode("utf-8", errors="replace")


def _frame(path: Path, at: float, size=224, *, preserve_aspect=False):
    from PIL import Image
    if preserve_aspect:
        raw = _run(["ffmpeg", "-nostdin", "-v", "error", "-threads", "1", "-ss", f"{at:.4f}",
                    *_INPUT_GUARDS, "-i", str(path), "-frames:v", "1", "-vf", f"scale={size}:{size}:force_original_aspect_ratio=decrease",
                    "-threads", "1", "-f", "image2pipe", "-c:v", "png", "-"], raw=True, timeout=25)
        try:
            with Image.open(io.BytesIO(raw)) as im:
                return im.convert("RGB")
        except (OSError, ValueError) as exc:
            raise ValidationError("Video frame could not be decoded") from exc
    raw = _run(["ffmpeg", "-nostdin", "-v", "error", "-threads", "1", "-ss", f"{at:.4f}",
                *_INPUT_GUARDS, "-i", str(path), "-frames:v", "1", "-vf", f"scale={size}:{size}",
                "-threads", "1", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"], raw=True, timeout=25)
    if len(raw) != size * size * 3:
        raise ValidationError("Video frame could not be decoded")
    return Image.frombytes("RGB", (size, size), raw)


def localized_motion_evidence(frames):
    """Second-stage motion check for quiet nature footage.

    Detect persistent spatial changes at higher resolution while rejecting
    uniform brightness fluctuations, frozen pictures and one-off cuts.
    This is a screening signal, not proof of documentary authenticity.
    """
    from PIL import Image, ImageChops, ImageFilter, ImageStat
    if len(frames) != 8:
        raise ValueError("Expected four adjacent frame pairs")
    samples = [f.convert("L").resize((192,192)).filter(
        ImageFilter.GaussianBlur(.8)) for f in frames]
    counts, changed_regions, strengths = [], [], []
    for i in (0,2,4,6):
        # Signed change, centered around the frame-wide median, removes
        # uniform exposure variation; blur suppresses compression noise.
        signed = ImageChops.subtract(samples[i+1],samples[i],scale=2,offset=128)
        center = int(ImageStat.Stat(signed).median[0])
        residual = ImageChops.difference(signed,Image.new("L",signed.size,center))
        active = set()
        for y in range(0,192,24):
            for x in range(0,192,24):
                tile=residual.crop((x,y,x+24,y+24))
                hist=tile.histogram()
                # 4 signed units correspond to about 8 luma levels.
                if sum(hist[4:]) >= 30 and ImageStat.Stat(tile).mean[0] >= .7:
                    active.add((x//24,y//24))
        counts.append(len(active))
        changed_regions.append(active)
        strengths.append(ImageStat.Stat(residual).mean[0])
    passing=sum(x>=2 for x in counts)
    repeated=sum(sum(tile in group for group in changed_regions)>=3
                 for tile in set().union(*changed_regions))
    return {"passed":passing>=3 and repeated>=1,
            "active_tiles_per_pair":counts,"repeated_tiles":repeated,
            "mean_residual":round(statistics.median(strengths),4)}


class QualityValidator:
    def __init__(self, min_short_side=720, *, min_fps=15, max_duration=1800):
        self.min_short_side = min_short_side
        self.min_fps = min_fps
        self.max_duration = max_duration

    def validate(self, path: Path, need=0, *, allow_calm_crop=False) -> dict:
        from PIL import ImageChops, ImageFilter, ImageStat
        data = json.loads(_run(["ffprobe", "-v", "error", *_INPUT_GUARDS, "-show_streams", "-show_format", "-of", "json", str(path)]))
        streams = [s for s in data.get("streams", []) if s.get("codec_type") == "video"
                   and not s.get("disposition", {}).get("attached_pic")]
        if not streams:
            raise ValidationError("File has no moving video stream")
        video = streams[0]
        coded_width, coded_height = int(video.get("width", 0)), int(video.get("height", 0))
        rotation = float(video.get("tags", {}).get("rotate") or 0)
        for side_data in video.get("side_data_list", []):
            if "rotation" in side_data:
                rotation = float(side_data["rotation"])
        width, height = coded_width, coded_height
        if round(rotation) % 180 == 90:
            width, height = height, width
        codec = video.get("codec_name") or ""
        if codec in ("png", "jpeg", "mjpeg", "bmp", "gif", "webp") or not codec:
            raise ValidationError("Image codecs are forbidden")
        fraction = str(video.get("avg_frame_rate") or "0/1").split("/")
        try:
            fps = float(fraction[0]) / (float(fraction[1]) if len(fraction) > 1 else 1)
            duration = float(video.get("duration") or data.get("format", {}).get("duration") or 0)
        except (ValueError, ZeroDivisionError) as exc:
            raise ValidationError("Invalid video timing") from exc
        if not math.isfinite(fps) or not math.isfinite(duration):
            raise ValidationError("Invalid video timing")
        if min(width, height) < self.min_short_side:
            raise ValidationError(f"Source is {width}x{height}; requires short side >= {self.min_short_side}")
        if fps < self.min_fps or fps > 240:
            raise ValidationError(f"Unusable source frame rate: {fps}")
        if duration < max(float(need), 0.6) or duration > self.max_duration:
            raise ValidationError(f"Source duration {duration:.3f}s cannot cover {need}s without looping")
        # Sample across the portion that will actually be used, including adjacent
        # frames to distinguish motion from simple scene changes in a slideshow.
        span = min(duration - 0.12, max(2, float(need) or 6))
        times = [max(0, span * p) for p in (0, .08, .33, .41, .66, .74, .91, .99)]
        frames = [_frame(path, at, 64).convert("L") for at in times]
        stats = [ImageStat.Stat(frame) for frame in frames]
        brightness = [s.mean[0] for s in stats]
        detail = [s.stddev[0] for s in stats]
        edges = [ImageStat.Stat(f.filter(ImageFilter.FIND_EDGES).crop((2, 2, 62, 62))).mean[0] for f in frames]
        changes = [ImageStat.Stat(ImageChops.difference(frames[i], frames[i + 1])).mean[0]
                   for i in (0, 2, 4, 6)]
        if statistics.median(brightness) < 5 or max(detail) < 5 or statistics.median(edges) < 1.0:
            raise ValidationError("Black, blank or insufficient-detail video rejected")
        motion_mode = "standard"
        local_motion = None
        if statistics.median(changes) < .65 or sum(c >= .65 for c in changes) < 3:
            # Keep existing acceptance criteria intact. Only failed
            # candidates receive the more expensive higher-resolution check.
            local_motion = localized_motion_evidence(
                [_frame(path, at, 192) for at in times])
            if not local_motion["passed"]:
                if not allow_calm_crop:
                    raise ValidationError("Static or insufficiently moving footage rejected; "
                        "local motion tiles="+str(local_motion["active_tiles_per_pair"])
                        +", repeated="+str(local_motion["repeated_tiles"]))
                # Only the derived center crop of an independently verified
                # moving source may use this exception. Blank, damaged and
                # low-detail frames still fail the preceding technical gates.
                motion_mode = "calm_verified_source_crop"
                print("[CALM CROP; NO MOTION CLAIM]",local_motion,flush=True)
            else:
                motion_mode = "localized_slow_motion"
                print("[SLOW MOTION VERIFIED]",local_motion,flush=True)
        # This scale is reported explicitly: a 1920x1080 landscape source can
        # meet source-HD policy while still requiring enlargement after 9:16 crop.
        target_width, target_height = (int(v) for v in os.environ.get("RESOLUTION", "720x1280").lower().split("x"))
        portrait_crop_width = min(width, height * target_width / target_height)
        return {"width": width, "height": height, "coded_width": coded_width, "coded_height": coded_height,
                "rotation": rotation, "container": data.get("format", {}).get("format_name", ""), "fps": round(fps, 4), "duration": duration,
                "codec": codec, "source_full_hd": min(width, height) >= 1080,
                "source_4k": min(width, height) >= 2160,
                "portrait_crop_width": round(portrait_crop_width),
                "portrait_crop_scale": round(max(target_width / portrait_crop_width, target_height / height), 4),
                "motion_mode": motion_mode, "localized_motion": local_motion,
                "motion_score": round(statistics.median(changes), 4),
                "detail_score": round(statistics.median(edges), 4), "sample_times": times}


_STOP = set("a an the and or in on at of to with from for is are as by into up young close view footage video".split())
_SYNONYMS = {"euros": "euro", "banknotes": "banknote", "cash": "money", "banknote": "money", "bill": "money",
             "sidewalk": "pavement", "street": "pavement", "road": "pavement", "male": "man", "person": "human",
             "picks": "pick", "picking": "pick", "pickingup": "pick", "walking": "walk", "walks": "walk",
             "running": "run", "runs": "run", "swimming": "swim", "swims": "swim",
             "volcanic": "volcano", "volcanoes": "volcano", "volcanos": "volcano",
             "erupting": "erupt", "eruption": "erupt", "eruptions": "erupt",
             "exploding": "explod", "explosion": "explod", "explosions": "explod",
             "burning": "burn", "blazing": "burn", "flames": "fire", "flame": "fire",
             "flying": "fly", "flight": "fly", "flights": "fly",
             "aircraft": "airplane", "planes": "airplane", "plane": "airplane",
             "aeroplane": "airplane", "caverns": "cave", "cavern": "cave",
             "glacial": "glacier", "glaciers": "glacier"}


def _stem(word: str) -> str:
    # Resolve aliases such as banknotes -> banknote -> money before stemming.
    while word in _SYNONYMS and _SYNONYMS[word] != word:
        word = _SYNONYMS[word]
    if word.endswith("ies") and len(word) > 4:
        word = word[:-3] + "y"
    elif word.endswith(("ches", "shes", "sses", "xes", "zes")):
        word = word[:-2]
    elif word.endswith("s") and len(word) > 3 and not word.endswith(("ss", "us", "is")):
        word = word[:-1]
    if word.endswith("ing") and len(word) > 5:
        word = word[:-3]
    elif word.endswith("ed") and len(word) > 4:
        word = word[:-2]
    if len(word) > 3 and word[-1] == word[-2] and word[-1] not in "ls":
        word = word[:-1]
    if len(word) > 3 and word.endswith("e"):
        word = word[:-1]
    return _SYNONYMS.get(word, word)


def _terms(value: str) -> set[str]:
    from scene_relevance import english
    words = re.findall(r"[a-z]+|[0-9]+", english(value))
    return {_stem(w) for w in words if w not in _STOP and len(w) > 1}


def _documentary_metadata_terms(value: str) -> set[str]:
    """Resolve well-known stock labels before literal metadata screening.

    Aurora is often catalogued as 'northern lights', and vice versa. This
    expands only independently present descriptive keywords, never inserts
    requested topic words into unrelated source metadata.
    """
    terms = _terms(value)
    aurora = _terms("aurora borealis")
    northern_lights = _terms("northern lights")
    if (terms & aurora) or northern_lights.issubset(terms):
        terms.update(aurora)
        terms.update(northern_lights)
    return terms


def scene_specific_hard_negatives(spec):
    """Contrast requested subject with plausible but misleading B-roll.

    A generic 'portrait indoors' negative cannot catch a person WALKING
    outdoors during narration about clouds, or a sunset substituted for a
    clear blue daytime sky. These comparisons reuse local CLIP, no paid API.
    """
    if not isinstance(spec, SceneSpec):
        spec = SceneSpec.from_dict(spec)
    subject = str(spec.object).casefold()
    query = str(spec.visual_search_query).casefold()
    no_actor = not str(spec.main_character).strip()
    from video_first_policy import contrast_prompts
    targeted=contrast_prompts(subject,query)
    if not no_actor:
        return targeted
    nature = {"sky", "sun", "sunlight", "cloud", "clouds", "atmosphere",
              "rain", "snow", "river", "ocean", "sea", "wave", "water",
              "forest", "mountain", "lightning", "volcano", "iceberg"}
    terms = _terms(subject)
    if not terms & set().union(*(_terms(w) for w in nature)):
        return targeted
    negative = [
        "A close-up photograph of a person's face outside.",
        "A person walking outdoors with nature in the background.",
    ]
    if "blue" in query and "sky" in query:
        negative.extend([
            "Orange sunset clouds over buildings without a blue sky.",
            "A gray overcast sky above an urban city.",
        ])
    if "sunlight" in subject and "cloud" in query:
        negative.append(
            "A silhouette of a person walking at sunset with no visible sunlight rays.")
    return negative+targeted


class SceneMatcher:
    """Require metadata grounding plus sampled local CLIP evidence.

    Scores are raw cosine similarity, with a margin against generic and wrong
    subject captions. No threshold can certify an exact denomination or identity.
    """
    _model = None
    _processor = None
    _lock = threading.RLock()

    def __init__(self, *, threshold=None, margin=.0):
        self.threshold = float(threshold if threshold is not None else os.environ.get("PURFFLE_CLIP_THRESHOLD", ".22"))
        self.margin = margin

    @staticmethod
    def metadata_score(spec: SceneSpec, metadata: str) -> float:
        have = _documentary_metadata_terms(metadata)
        wanted = _documentary_metadata_terms(spec.visual_search_query)
        if not have or not wanted:
            return 0.0
        return len(wanted & have) / len(wanted)

    @classmethod
    def validate_metadata(cls, spec: SceneSpec, metadata: str) -> float:
        """Apply the full scene gate before downloading or running visual inference."""
        if not isinstance(spec, SceneSpec):
            spec = SceneSpec.from_dict(spec)
        if not spec.object or not spec.action or not spec.visual_search_query:
            raise ValidationError("Incomplete structured scene")
        score = cls.metadata_score(spec, metadata)
        have = _documentary_metadata_terms(metadata)
        # Stock descriptions rarely mention camera movement or lighting.
        # A named landmark is sufficient for metadata preflight ONLY when its
        # distinctive name occurs in the provider's description. The downloaded
        # frames must still pass the separate local CLIP visual verifier.
        landmark_names = ("stonehenge", "machu picchu", "giza", "easter island", "moai")
        query_text = spec.visual_search_query.lower()
        metadata_text = metadata.lower()
        named_landmark = next((name for name in landmark_names
                               if name in query_text and name in metadata_text), None)
        if named_landmark and score >= .20:
            return score
        # Atmospheric stock clips are often tagged only with their visible subject
        # (e.g. "sky", "sunrise") rather than an invented camera/light action.
        # Allow subject-grounded scenery through metadata preflight, but still
        # require local frame-level CLIP verification before accepting a clip.
        scenery_subjects = {"sky", "sun", "sunris", "sunset", "cloud", "clouds",
                            "horizon", "ocean", "sea", "mountain", "forest",
                            "river", "lake", "rain", "snow", "star", "moon",
                            "landscap", "field", "beach", "wave", "aurora", "borealis"}
        # For explicitly marked, contextual establishing shots only. These are
        # *not* permission to ignore an ordinary requested human/animal action.
        contextual_scenery = {"cav", "glacier", "ice", "iceberg", "desert",
                              "dun", "sand", "waterfall", "coast", "geotherm",
                              "water", "landscap", "ocean", "seafloor",
                              "volcano", "lava", "fire", "snake", "forest",
                              "tree", "branch", "pine", "island", "storm",
                              "lightning", "snow", "submarine",
                              "earth", "telescope", "ship", "airplane",
                              "building", "street", "ruin", "city", "star", "aurora", "borealis"}
        # The matcher stems words ("snake"->"snak", "fire"->"fir").
        # Normalize the visible-subject allowlists the SAME way, otherwise
        # genuinely matching stock footage is silently rejected.
        scenery_subjects = set().union(*(_terms(word) for word in scenery_subjects))
        contextual_scenery = set().union(*(_terms(word) for word in contextual_scenery))
        scenery_actions = {"glow", "shin", "ris", "set", "mov", "drift",
                           "flow", "blow", "fall", "spark", "twinkl",
                           "brighten", "darken", "appear", "chang"}
        object_terms = _terms(spec.object)
        action_terms = _terms(spec.action)
        query_terms = _documentary_metadata_terms(spec.visual_search_query)
        # Scenery has no human-style action to tag: "sky overhead" and
        # "clouds drifting" are both legitimate stock-video descriptions.
        # Only bypass action wording for scenes without a character, with a
        # scenery object actually named in the provider metadata. The separate
        # downloaded-video motion, quality and CLIP checks still apply.
        scenery_core = (object_terms | query_terms) & scenery_subjects
        character = spec.main_character.strip().lower()
        no_character = character in ("", "none", "no character", "n/a", "null", "not applicable", "no person")
        # Existing natural scenery can be preflighted by visible nouns. The
        # actual frames must independently pass CLIP and real motion checks.
        # A matching background is not enough when the requested object
        # includes a more specific subject (e.g. water *droplets*).
        # Require ALL explicit object nouns; the video frame is still checked.
        if (scenery_core and scenery_core.issubset(have)
                and object_terms and object_terms.issubset(have)
                and no_character and score >= .20):
            return score
        # A clearly labeled illustrative establishing shot may show a cave,
        # glacier or desert without metadata claiming the impossible action
        # ("the cave is moving", "sand dunes forming a perfect circle").
        # Require its actual visible object and a specifically ambient intent.
        contextual_core = object_terms & (contextual_scenery | scenery_subjects)
        if (no_character and action_terms == {"ambient"} and object_terms
                and object_terms.issubset(contextual_core)
                and contextual_core.issubset(have) and score >= .15):
            return score
        # User-requested bathroom condensation B-roll: providers typically
        # label an actually visible mirror ("mirror", "reflection") or a
        # running shower, but never the synthetic action word "ambient".
        # Keep this exceptionally narrow: no character, deliberately ambient,
        # exact source object noun present, and a recognizable bathroom-mirror
        # or shower stock query. This is ONLY a metadata preflight; actual
        # downloaded frames still need local CLIP, motion, resolution, length,
        # duplicate and license validation. Never mistake a meteor shower,
        # concert or generic scenery for footage of a bathroom shower.
        domestic_objects = {"mirror", "shower"}
        domestic_object = object_terms & domestic_objects
        domestic_query = bool(query_terms & _terms("mirror bathroom shower"))
        if (no_character and action_terms == {"ambient"}
                and object_terms and object_terms.issubset(domestic_objects)
                and domestic_object.issubset(have)
                and domestic_query and score >= .25):
            if "shower" in domestic_object:
                bath_context = _terms("bathroom bath bathing water showerhead steam bathtub wet")
                non_bath = _terms("meteor cosmic astronomy stars sky space golden")
                if not (have & bath_context - _terms("shower")) or have & non_bath:
                    raise ValidationError(
                        "Bathroom shower metadata lacks domestic water context")
            return score
        # Wildlife stock is usually tagged by species rather than behavior.
        # For documentary B-roll without a named character, a matching animal
        # subject is enough for preflight. CLIP still verifies downloaded frames.
        wildlife = {"dolphin", "whale", "shark", "turtle", "bird", "eagle",
                    "penguin", "elephant", "lion", "tiger", "bear", "wolf",
                    "fox", "deer", "fish", "octopus", "seal", "jellyfish"}
        # Match wildlife nouns after the SAME stemming used by provider metadata.
        # 'turtle' -> 'turtl' and 'whale' -> 'whal'; unnormalised names
        # silently rejected genuine HD wildlife footage at metadata preflight.
        wildlife = set().union(*(_terms(word) for word in wildlife))
        wildlife_core = object_terms & wildlife
        if (no_character and wildlife_core and wildlife_core.issubset(have)
                and score >= .20):
            return score
        # Natural close-ups (rain drops, water droplets, sunlight, mist) are
        # tagged by visible subjects, not by the complete poetic lighting action
        # invented by an LLM. Require every explicit object noun in the stock
        # metadata; verify actual frames, motion, quality and license afterward.
        # This is intentionally NOT applied to people, money or manufactured
        # objects, where the exact requested action is essential.
        nature_objects = {"water", "droplet", "drop", "rain", "mist", "fog",
                          "haze", "sunlight", "light", "ray", "snow", "ice",
                          "rainbow", "dew", "reflection", "reflect", "cloud",
                          "clouds", "sky", "sun", "lake", "river", "ocean",
                          "sea", "wave", "mountain", "forest", "field"}
        if (no_character and object_terms and object_terms.issubset(nature_objects)
                and object_terms.issubset(have) and score >= .15):
            return score
        # A shared location or generic 'man' cannot compensate for a missing object.
        # Search tags are terse: a two-of-five keyword match (0.400) can still be useful when the
        # actual object AND action are explicitly named. Require both;
        # the downloaded frames must independently pass local CLIP.
        object_terms = _terms(spec.object)
        action_terms = _terms(spec.action)
        object_grounded = bool(object_terms) and object_terms.issubset(have)
        action_grounded = bool(action_terms) and bool(action_terms & have)
        if not object_grounded:
            raise ValidationError(f"Scene metadata lacks object/action grounding (score {score:.3f})")
        if score < .40:
            raise ValidationError(f"Scene metadata lacks object/action grounding (score {score:.3f})")
        if not action_grounded:
            raise ValidationError("Scene metadata does not describe the requested action")
        return score

    @classmethod
    def _load(cls):
        with cls._lock:
            if cls._model is not None:
                return
            try:
                import torch
                from transformers import CLIPModel, CLIPProcessor
                torch.set_num_threads(max(1, min(2, os.cpu_count() or 1)))
                model_id = os.environ.get("PURFFLE_CLIP_MODEL", "openai/clip-vit-base-patch32")
                options = {"local_files_only": os.environ.get("PURFFLE_CLIP_LOCAL_ONLY") == "1"}
                cls._processor = CLIPProcessor.from_pretrained(model_id, **options)
                cls._model = CLIPModel.from_pretrained(model_id, **options).eval()
            except Exception as exc:
                cls._model = cls._processor = None
                raise ValidationError("Local visual verifier unavailable; scene cannot be accepted") from exc

    def _similarities(self, images, captions):
        self._load()
        import torch
        with self._lock, torch.inference_mode():
            from PIL import ImageOps
            # Preserve the entire frame; the default CLIP center crop can hide a
            # subject close to a landscape frame's left or right edge.
            images = [ImageOps.pad(im, (224, 224), color=(127, 127, 127)) for im in images]
            inputs = self._processor(text=captions, images=images, return_tensors="pt", padding=True,
                                     truncation=True, max_length=77)
            output = self._model(**inputs)
            scale = self._model.logit_scale.exp()
            return (output.logits_per_image / scale).cpu().tolist()

    def match(self, path: Path, spec: SceneSpec, metadata="", *, duration=None) -> dict:
        if not isinstance(spec, SceneSpec):
            spec = SceneSpec.from_dict(spec)
        metadata_score = self.validate_metadata(spec, metadata)
        if duration is None:
            duration = float(json.loads(_run(["ffprobe", "-v", "error", *_INPUT_GUARDS, "-show_entries", "format=duration", "-of", "json", str(path)]))["format"]["duration"])
        frames = [_frame(path, max(0, min(float(duration) - .15, t)), 448, preserve_aspect=True)
                  for t in (0.2, float(duration) * .35, float(duration) * .7)]
        positive = f"A real video frame of {spec.visual_search_query}."
        # A cave or underwater seafloor is not an 'outdoor photograph'.
        # Keep the verifier focused on the actual requested visible subject.
        object_caption = (f"A documentary video frame showing {spec.object}." if not spec.main_character.strip()
                          else f"A photograph showing {spec.main_character} {spec.object}.")
        negatives = ["A person playing a guitar.", "Electronic devices on a desk.", "A person riding a skateboard.",
                     "A static illustration or abstract colorful background."]
        negatives = [c for c in negatives if not (_terms(spec.object) & _terms(c))]
        if spec.main_character.strip():
            negatives.append(f"An empty {spec.location or 'location'} with nobody present.")
        else:
            negatives.append("A close-up portrait of a person indoors.")
        # Generic negative pictures were too easy to beat. In the actual
        # blue-sky Short a person walking at sunset was chosen for sunlight
        # and a gray cloudy urban sky stood in for clear blue daylight.
        negatives.extend(scene_specific_hard_negatives(spec))
        captions = [positive, object_caption] + negatives
        scores = self._similarities(frames, captions)
        positive_scores = [row[0] for row in scores]
        object_scores = [row[1] for row in scores]
        margins = [row[0] - max(row[2:]) for row in scores]
        visual_score = statistics.median(positive_scores)
        object_score = statistics.median(object_scores)
        visual_margin = statistics.median(margins)
        # Two actual sampled moments must beat competing, plausible B-roll,
        # not only the generic computer/guitar negatives. This remains an
        # uncalibrated ranking gate, not proof of factual visual entailment.
        requested_clear_blue_sky = ("blue" in spec.visual_search_query.casefold()
                                    and "sky" in spec.visual_search_query.casefold())
        required_margin = max(self.margin, .018 if requested_clear_blue_sky else
                              .008 if scene_specific_hard_negatives(spec) else .0)
        matching_moments = sum(
            row[0] >= self.threshold and
            row[0] - max(row[2:]) >= required_margin
            for row in scores)
        if (visual_score < self.threshold or object_score < self.threshold - .055
                or visual_margin < required_margin
                or matching_moments < 2):
            raise ValidationError(f"Visual scene mismatch: cosine={visual_score:.3f}, object={object_score:.3f}, margin={visual_margin:.3f}")
        # Coarse horizontal localization: compare three 9:16 windows in the
        # source frame. The renderer may consume crop_focus_x to retain subject.
        # Localization is a three-window heuristic, not temporal tracking.
        windows = []
        center_frame = frames[1]
        w, h = center_frame.size
        crop_w = min(w, int(h * 9 / 16))
        edge = crop_w / (2 * w)
        centers = (edge, .5, 1 - edge)
        for center in centers:
            left = max(0, min(w - crop_w, int(center * w - crop_w / 2)))
            windows.append(center_frame.crop((left, 0, left + crop_w, h)))
        crop_scores = self._similarities(windows, [object_caption])
        best = max(range(3), key=lambda i: crop_scores[i][0])
        return {"metadata_score": round(metadata_score, 4), "visual_score": round(visual_score, 4),
                "object_score": round(object_score, 4), "visual_margin": round(visual_margin, 4),
                "threshold": self.threshold, "model": os.environ.get("PURFFLE_CLIP_MODEL", "openai/clip-vit-base-patch32"),
                "sample_scores": positive_scores, "crop_focus_x": centers[best],
                "scene_hard_negative_count": len(scene_specific_hard_negatives(spec)),
                "required_visual_margin": round(required_margin, 4),
                "matching_moments": matching_moments,
                "verification": "local_clip_screening", "limitations": "Similarity screening cannot prove exact actions, identity or denomination."}


def download_hd_variant(item, downloader, validator, *, need=0, check=None,
                        segment_seconds=0, segment_check=None):
    """Normal licensed download, official HD variants, and bounded partial
    extraction when the remote server supports verified byte ranges."""
    extra = getattr(item, "extra", {}) or {}
    variants = extra.get("download_variants") or []
    urls = list(dict.fromkeys([item.url, *variants]))[:4]
    last = None
    range_candidates = []
    range_failures = []
    range_attempts = []
    if hasattr(item, "extra"):
        item.extra["partial_attempts"] = range_attempts
    segment_seconds = min(90., max(float(segment_seconds or 0), float(need or 0)+.3))
    # Keep ordinary stock fast. Known long assets may be sliced before their
    # full download; unknown-size assets fall back after the normal byte cap.
    known_duration = float(getattr(item, "duration", 0) or 0)
    prefer_range = (segment_seconds >= 1 and known_duration > max(120, 4*segment_seconds)
                    and getattr(item, "source", "") != "coverr-video")
    def accept(path, evidence):
        quality = validator.validate(path, need=need) if need else validator.validate(path)
        if evidence["mode"] == "http_range":
            requested = evidence["requested_seconds"]
            if float(quality["duration"]) < max(float(need or 0),requested-.6):
                raise ValidationError("Partial clip shorter than requested interval")
        if check is not None and not check(quality):
            raise ValidationError("Source variant does not meet output framing requirements")
        if segment_check is not None:
            segment_check(path, quality)
        if hasattr(item,"extra"):
            item.extra["download_evidence"] = evidence
        return path,quality
    def partial(url):
        from range_segment import extract_segment
        # A long recording may begin with a slate, black frames or a static
        # title. Try later actual footage rather than relaxing HD/motion gates.
        # All range-capable sources can contain useful later footage.
        # Keep the per-rendition limit at three intervals and the existing
        # per-interval byte/time caps. A server refusing ranges stops retries.
        offsets = [0.,max(20.,segment_seconds+5),max(60.,2*segment_seconds+10)]
        if known_duration > 0:
            offsets = [x for x in offsets if x+segment_seconds <= known_duration+.1] or [0.]
        failure = None
        for offset in offsets:
            try:
                path,evidence=extract_segment(url,downloader,segment_seconds,offset=offset)
            except Exception as exc:
                failure=exc
                range_attempts.append({"offset":offset,"status":"transfer_failed",
                    "reason":re.sub(r"https?://\S+","[url omitted]",str(exc))[:180]})
                print("[PARTIAL TRANSFER REJECT]", getattr(item,"source","unknown"),
                      offset,range_attempts[-1]["reason"],flush=True)
                # No later seek helps when the server itself refuses ranges.
                break
            try:
                result=accept(path,evidence)
                range_attempts.append({**evidence,"status":"quality_passed"})
                return result
            except Exception as exc:
                failure=exc
                path.unlink(missing_ok=True)
                reason=re.sub(r"https?://\S+","[url omitted]",str(exc))[:180]
                range_attempts.append({**evidence,"status":"quality_rejected","reason":reason})
                print("[PARTIAL QUALITY REJECT]",getattr(item,"source","unknown"),offset,reason,flush=True)
                # Resolution cannot be improved by seeking within one encode.
                if "requires short side" in reason or "framing requirements" in reason:
                    break
        if failure is not None:
            range_failures.append(failure)
            raise failure
        raise ValidationError("No usable partial interval")
    for url in urls:
        if prefer_range:
            try:
                return partial(url)
            except Exception as exc:
                last=exc
        try:
            return accept(downloader.download(url),{"mode":"full_download"})
        except Exception as exc:
            last=exc
            reason=str(exc).lower()
            if (not prefer_range and segment_seconds>=1
                and getattr(item,"source","")!="coverr-video"
                and any(x in reason for x in ("exceeds byte budget","time budget exceeded","transport failure"))):
                range_candidates.append(url)
            if len(urls)>1:
                print("[SOURCE VARIANT REJECT]",getattr(item,"source","unknown"),type(exc).__name__,flush=True)
    for url in range_candidates[:2]:
        try:
            return partial(url)
        except Exception as exc:
            print("[PARTIAL SOURCE REJECT]",getattr(item,"source","unknown"),
                  type(exc).__name__,str(exc)[:120],flush=True)
            last=exc
    if range_failures:
        # Preserve the actual partial-download/quality failure rather than
        # overwriting it with the later full-download size rejection.
        quality_failures = [x for x in range_attempts if x["status"]=="quality_rejected"]
        if quality_failures:
            raise ValidationError("Partial clip quality rejected: "+quality_failures[-1]["reason"])
        raise range_failures[-1]
    if last is not None:
        raise last
    raise ValidationError("No downloadable source variants")
