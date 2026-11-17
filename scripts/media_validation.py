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


class QualityValidator:
    def __init__(self, min_short_side=720, *, min_fps=15, max_duration=1800):
        self.min_short_side = min_short_side
        self.min_fps = min_fps
        self.max_duration = max_duration

    def validate(self, path: Path, need=0) -> dict:
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
        if statistics.median(changes) < .65 or sum(c >= .65 for c in changes) < 3:
            raise ValidationError("Static or insufficiently moving footage rejected")
        # This scale is reported explicitly: a 1920x1080 landscape source can
        # meet source-HD policy while still requiring enlargement after 9:16 crop.
        portrait_crop_width = min(width, height * 9 / 16)
        return {"width": width, "height": height, "coded_width": coded_width, "coded_height": coded_height,
                "rotation": rotation, "container": data.get("format", {}).get("format_name", ""), "fps": round(fps, 4), "duration": duration,
                "codec": codec, "source_full_hd": min(width, height) >= 1080,
                "source_4k": min(width, height) >= 2160,
                "portrait_crop_width": round(portrait_crop_width),
                "portrait_crop_scale": round(max(1080 / portrait_crop_width, 1920 / height), 4),
                "motion_score": round(statistics.median(changes), 4),
                "detail_score": round(statistics.median(edges), 4), "sample_times": times}


_STOP = set("a an the and or in on at of to with from for is are as by into up young close view footage video".split())
_SYNONYMS = {"euros": "euro", "banknotes": "banknote", "cash": "money", "banknote": "money", "bill": "money",
             "sidewalk": "pavement", "street": "pavement", "road": "pavement", "male": "man", "person": "human",
             "picks": "pick", "picking": "pick", "pickingup": "pick", "walking": "walk", "walks": "walk",
             "running": "run", "runs": "run", "swimming": "swim", "swims": "swim"}


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
    words = re.findall(r"[a-z]+|[0-9]+", value.lower())
    return {_stem(w) for w in words if w not in _STOP and len(w) > 1}


class SceneMatcher:
    """Require metadata grounding plus sampled local CLIP evidence.

    Scores are raw cosine similarity, with a margin against generic and wrong
    subject captions. No threshold can certify an exact denomination or identity.
    """
    _model = None
    _processor = None
    _lock = threading.RLock()

    def __init__(self, *, threshold=None, margin=.015):
        self.threshold = float(threshold if threshold is not None else os.environ.get("PURFFLE_CLIP_THRESHOLD", ".26"))
        self.margin = margin

    @staticmethod
    def metadata_score(spec: SceneSpec, metadata: str) -> float:
        have = _terms(metadata)
        wanted = _terms(spec.visual_search_query)
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
        have = _terms(metadata)
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
        # A shared location or generic 'man' cannot compensate for a missing object.
        # Search tags are terse: a two-of-five keyword match (0.400) can still be useful when the
        # actual object AND action are explicitly named. Require both;
        # the downloaded frames must independently pass local CLIP.
        object_terms = _terms(spec.object)
        action_terms = _terms(spec.action)
        object_grounded = bool(object_terms) and object_terms.issubset(have)
        action_grounded = bool(action_terms) and bool(action_terms & have)
        if not object_grounded and not (score >= .50 and action_grounded):
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
        object_caption = f"A photograph showing {spec.main_character} {spec.object}."
        negatives = ["A person playing a guitar.", "Electronic devices on a desk.", "A person riding a skateboard.",
                     "A static illustration or abstract colorful background."]
        negatives = [c for c in negatives if not (_terms(spec.object) & _terms(c))]
        negatives.append(f"An empty {spec.location or 'location'} with nobody present.")
        captions = [positive, object_caption] + negatives
        scores = self._similarities(frames, captions)
        positive_scores = [row[0] for row in scores]
        object_scores = [row[1] for row in scores]
        margins = [row[0] - max(row[2:]) for row in scores]
        visual_score = statistics.median(positive_scores)
        object_score = statistics.median(object_scores)
        visual_margin = statistics.median(margins)
        if (visual_score < self.threshold or object_score < self.threshold - .025
                or visual_margin < self.margin
                or sum(s >= self.threshold for s in positive_scores) < 2):
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
                "verification": "local_clip_screening", "limitations": "Similarity screening cannot prove exact actions, identity or denomination."}
