"""Official API adapters for real footage. No scraping, images or permissive fallbacks.

Reported dimensions are hints; media_quality validates the downloaded file. API responses
are cached for 24 hours (including empty searches), never API keys or error bodies.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urlparse, parse_qs

import requests

HEADERS = {"User-Agent": "PurffleVideoStudio/2.0 (https://github.com/ahmedsaleh200507-prog/purffle-video-studio)"}
API = "https://commons.wikimedia.org/w/api.php"
VIDEO_MIMES = {"video/mp4", "video/webm", "video/ogg", "application/ogg", "video/quicktime", "video/mpeg"}
NASA_POLICY = "https://www.nasa.gov/nasa-brand-center/images-and-media/"


def clean(value):
    if isinstance(value, list):
        return " ".join(clean(x) for x in value)
    return html.unescape(re.sub(r"<[^>]*>", "", str(value or ""))).strip()


def sequence(value):
    return value if isinstance(value, list) else ([value] if value else [])


def secure_url(value):
    try:
        p = urlparse(value)
        return p.scheme == "https" and bool(p.hostname) and not p.username and not p.password
    except (TypeError, ValueError):
        return False


def video_url(value):
    return secure_url(value) and bool(re.search(r"\.(?:mp4|webm|ogv|ogg|mov|m4v|mpg|mpeg)(?:[?#]|$)", value, re.I))


class LicenseValidator:
    """Small allowlist, with complete attribution for CC BY. SA/NC/ND are excluded.

    This validates provider declarations; an upload is never proof of ownership.
    Model/privacy/trademark restrictions continue to apply to stock footage.
    """
    STOCK = {
        "PIXABAY": "https://pixabay.com/service/license-summary/",
        "PEXELS": "https://www.pexels.com/license/",
        "COVERR": "https://coverr.co/license",
        "NASA-MEDIA": NASA_POLICY,
    }

    @classmethod
    def identify(cls, url, label=""):
        p = urlparse(str(url or ""))
        if p.scheme in {"http", "https"} and p.hostname in {"creativecommons.org", "www.creativecommons.org"}:
            path = p.path.lower()
            if re.fullmatch(r"/publicdomain/zero/1\.0/?", path):
                return "CC0-1.0"
            if re.fullmatch(r"/publicdomain/mark/1\.0/?", path):
                return "PDM-1.0"
            m = re.fullmatch(r"/licenses/by/([1-4]\.0)/?", path)
            if m:
                return "CC-BY-" + m.group(1)
        return ""  # A licence name or a substring in a URL is insufficient.

    @classmethod
    def validate(cls, license_info):
        if not isinstance(license_info, dict):
            return False
        lid = license_info.get("id", "")
        url = license_info.get("url", "")
        if not secure_url(license_info.get("source_page", "")):
            return False
        if lid in cls.STOCK:
            return url == cls.STOCK[lid] and bool(license_info.get("creator"))
        if lid != cls.identify(url):
            return False
        if lid in {"CC0-1.0", "PDM-1.0"}:
            return True
        return lid.startswith("CC-BY-") and bool(clean(license_info.get("creator")))


class ProviderError(RuntimeError):
    def __init__(self, status, detail=""):
        self.status, self.detail = status, detail
        super().__init__(status + (": " + detail if detail else ""))


class JsonClient:
    """Bounded JSON transport with hashed credential-aware persistent caching.

    Serialize network calls to protect free quotas. A 429 causes a provider circuit
    breaker in ProviderRegistry; no repeated requests during the current video.
    """
    _lock = threading.Lock()
    _last_request = {}

    def __init__(self, cache_dir=Path("media_cache/api"), session=None, ttl=86400):
        self.cache_dir = Path(cache_dir)
        self.session = session or requests.Session()
        self.ttl = ttl

    def get(self, url, params=None, headers=None):
        headers = {**HEADERS, **(headers or {})}
        # Coverr returns signed JWT video links; never persist these in caches.
        sensitive_ephemeral = urlparse(url).hostname == "api.coverr.co"
        identity = json.dumps([url, params or {}, headers], sort_keys=True)
        cache = self.cache_dir / (hashlib.sha256(identity.encode()).hexdigest() + ".json")
        with self._lock:
            try:
                if not sensitive_ephemeral and cache.exists() and time.time() - cache.stat().st_mtime < self.ttl:
                    return json.loads(cache.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
            host = urlparse(url).hostname
            cooldown = self.cache_dir / (hashlib.sha256(str(host).encode()).hexdigest() + ".cooldown")
            try:
                if float(cooldown.read_text()) > time.time():
                    raise ProviderError("http_429", "persisted API quota cooldown is active")
            except (OSError, ValueError):
                pass
            # <= 60 calls/minute, below Pixabay's default 100/minute.
            # Independent matrix runners have separate API clocks. At two
            # concurrent workers, 1.6s per host stays under 100 queries/min.
            try:
                requested = float(os.environ.get("PURFFLE_API_INTERVAL_SECONDS", "1.05"))
            except (TypeError, ValueError):
                requested = 1.05
            interval = min(8.0, max(1.05, requested))
            pause = interval - (time.monotonic() - self._last_request.get(host, 0))
            if pause > 0:
                time.sleep(pause)
            try:
                response = self.session.get(url, params=params, headers=headers,
                                            timeout=(8, 25), stream=True, allow_redirects=False)
                self._last_request[host] = time.monotonic()
                with response:
                    if response.status_code != 200:
                        status = response.status_code
                        if status == 429:
                            self._save_cooldown(cooldown, response.headers)
                        raise ProviderError(f"http_{status}", "rate limited" if status == 429 else "request rejected")
                    if int(response.headers.get("Content-Length", "0")) > 4 * 1024 * 1024:
                        raise ProviderError("invalid_response", "JSON response exceeds 4 MiB")
                    chunks, size = [], 0
                    for part in response.iter_content(65536):
                        size += len(part)
                        if size > 4 * 1024 * 1024:
                            raise ProviderError("invalid_response", "JSON response exceeds 4 MiB")
                        chunks.append(part)
                    data = json.loads(b"".join(chunks))
                    if not isinstance(data, dict):
                        raise ProviderError("invalid_response", "expected JSON object")
                    if data.get("error"):
                        raise ProviderError("api_error", "API returned an error object")
                    if response.headers.get("X-RateLimit-Remaining") == "0":
                        self._save_cooldown(cooldown, response.headers)
            except ProviderError:
                raise
            except (requests.RequestException, ValueError, OSError):
                # Never return request URLs or response bodies: they may contain keys.
                raise ProviderError("network_or_json_error", "API request or JSON parsing failed") from None
            if not sensitive_ephemeral:
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                temp = cache.with_suffix(".tmp")
                temp.write_text(json.dumps(data), encoding="utf-8")
                temp.replace(cache)
            return data

    def patch(self, url, *, headers=None):
        """Report a Coverr clip download via official API, no exposed tokens."""
        if urlparse(url).hostname != "api.coverr.co" or not secure_url(url):
            raise ProviderError("unsafe_endpoint", "Expected official Coverr HTTPS API")
        try:
            response = self.session.patch(
                url, headers={**HEADERS, **(headers or {})},
                timeout=(8, 15), allow_redirects=False)
            with response:
                if response.status_code != 204:
                    raise ProviderError(f"http_{response.status_code}",
                                        "Coverr download tracking rejected")
        except ProviderError:
            raise
        except requests.RequestException:
            raise ProviderError("network_error", "Coverr download tracking unavailable") from None
        return True

    @staticmethod
    def _save_cooldown(path, headers):
        # Pixabay uses seconds-until-reset; Pexels can use an epoch reset. Retry-After
        # is preferred. Invalid/date-only headers conservatively wait one minute.
        now = time.time()
        delay = 60.0
        try:
            reset = float(headers.get("Retry-After") or headers.get("X-RateLimit-Reset") or 60)
            delay = reset - now if reset > 1000000 else reset
        except (TypeError, ValueError):
            pass
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(now + max(1, min(delay, 86400))))


@dataclass(frozen=True)
class VideoProvider:
    name: str
    key_env: str = ""
    policy_block: str = ""
    alternate_key_env: str = ""

    def unavailable_reason(self):
        if self.policy_block:
            return self.policy_block
        if self.key_env and not (
                os.environ.get(self.key_env, "").strip()
                or (self.alternate_key_env and
                    os.environ.get(self.alternate_key_env, "").strip())):
            return "missing " + self.key_env + (
                " or " + self.alternate_key_env if self.alternate_key_env else "")
        return ""


class ProviderHealthCheck:
    @staticmethod
    def check(provider):
        reason = provider.unavailable_reason()
        return {"provider": provider.name, "enabled": not bool(reason), "reason": reason,
                "api_test": "not_requested"}


PROVIDERS = [
    VideoProvider("pixabay", "PIXABAY_API_KEY"),
    VideoProvider("pexels", "PEXELS_API_KEY"),
    VideoProvider("wikimedia-video"), VideoProvider("nasa-video"),
    VideoProvider("archive-video"), VideoProvider("europeana-video", "EUROPEANA_API_KEY"),
    VideoProvider("nps-video", "NPS_API_KEY"),
    # Vecteezy Free requires attribution; the owner explicitly requests no
    # YouTube description/manual credits. Do not burn downloads or silently
    # assume a Pro license from the presence of an API key.
    VideoProvider("vecteezy-video", "VECTEEZY_API_KEY",
                  "free_license_requires_attribution_paid_license_unverified"),
    # No external API or website parsing. Offline allowlist of official CC0 MP4 URLs.
    VideoProvider("freenaturestock-video"),
    # Coverr Nov 4 2026: free commercial API use requires attribution and
    # tracking. We reject premium, sponsored, AI-generated stock media.
    VideoProvider("coverr-video", "COVERR_API_KEY",
                  alternate_key_env="COVER2"),
]


class ProviderRegistry:
    def __init__(self, MediaItem=None, cache_dir=Path("media_cache/api"), client=None):
        if MediaItem is None:
            from purffle_shorts.media import MediaItem
        self.MediaItem = MediaItem
        self.client = client or JsonClient(cache_dir)
        self.providers = {p.name: p for p in PROVIDERS}
        self.enabled = [p.name for p in PROVIDERS if not p.unavailable_reason()]
        self.events = []
        self._circuit = set()
        self._coverr_requests = 0
        self._event_lock = threading.Lock()

    def health(self):
        checks = []
        for p in self.providers.values():
            check = ProviderHealthCheck.check(p)
            check["circuit_open"] = p.name in self._circuit
            latest = next((e for e in reversed(self.events) if e["provider"] == p.name), None)
            if latest:
                check["last_status"] = latest["status"]
                check["api_test"] = latest["status"]
            checks.append(check)
        return checks

    def event(self, name, status, query="", count=0, detail=""):
        value = {"provider": name, "status": status, "query": query, "count": count, "detail": detail}
        with self._event_lock:
            self.events.append(value)
        print(f"[SOURCE CHECK] {name}: status={status} candidates={count} query={query!r} {detail}", flush=True)

    def search(self, source, query):
        provider = self.providers.get(source)
        if not provider:
            self.event(source, "unsupported", query)
            return []
        reason = provider.unavailable_reason()
        if reason:
            self.event(source, "skipped", query, detail=reason)
            return []
        if source in self._circuit:
            self.event(source, "circuit_open", query, detail="provider disabled after API rejection this video")
            return []
        try:
            found = getattr(self, "_" + source.replace("-video", ""))(query.strip())
            synthetic = re.compile(r"\banimat(?:ion|ions|ed)\b|\bCGI\b|computer[- ]generated|\bsimulation\b|\bAI[- ]generated\b|\bvisuali[sz]ation\b", re.I)
            # User publishes without writing a YouTube source description.
            # When set, reject CC-BY/Coverr and other credit-requiring content
            # BEFORE download; source discovery is not publication permission.
            no_credit = os.environ.get("PURFFLE_NO_ATTRIBUTION") == "1"
            items = [x for x in found if x.kind == "video" and secure_url(x.url)
                     and LicenseValidator.validate(x.extra.get("license"))
                     and not (no_credit and x.extra["license"].get("attribution_required"))
                     and not synthetic.search(x.text)]
            self.event(source, "ok" if items else "empty", query, len(items))
            return items
        except ProviderError as exc:
            if exc.status in {"http_401", "http_403", "http_429"}:
                self._circuit.add(source)
            self.event(source, exc.status, query, detail=exc.detail)
        except (KeyError, TypeError, ValueError, AttributeError):
            self.event(source, "invalid_schema", query, detail="API schema did not match documented response")
        return []

    def _item(self, source, identifier, url, query, rank, text, license_info, width=0, height=0, duration=0):
        if not secure_url(url) or not LicenseValidator.validate(license_info):
            return None
        item = self.MediaItem(source, str(identifier), "video", url, int(width or 0), int(height or 0),
                              duration=float(duration or 0), query=query, rank=rank, text=clean(text),
                              credit=" | ".join(str(license_info.get(k, "")) for k in ("creator", "id", "url", "source_page")))
        item.extra["license"] = license_info
        item.extra["metadata_reported"] = {"width": item.width, "height": item.height}
        return item

    @staticmethod
    def license(lid, url, creator, page):
        return {"id": lid, "url": url, "creator": clean(creator), "source_page": page,
                "attribution_required": lid.startswith("CC-BY-") or lid == "COVERR",
                "attribution": " | ".join([clean(creator), lid, url, page,
                    "Trimmed and cropped to vertical; original audio removed"]),
                "changes": "Trimmed and cropped to vertical; original audio removed"}

    @staticmethod
    def _files(files, url_field="url"):
        """Prefer genuine 1080p+ / 4K source variants. Unknown stays unknown."""
        files = [f for f in files if secure_url(f.get(url_field)) and
                 f.get("file_type", "video/mp4") == "video/mp4"]
        if not files:
            return None
        def score(f):
            w, h = int(f.get("width") or 0), int(f.get("height") or 0)
            short = min(w, h)
            if os.environ.get("PURFFLE_LONG_STOCK_HD_VARIANTS") == "1":
                # Long films render at 1080p. Choosing the largest 4K
                # CDN variant used to waste >110 MB per rejected clip;
                # select the native 1080p version when offered, and use
                # 720p footage only when no appropriate 1080p variant exists.
                # Shorts still use the original high-detail preference.
                native_hd = 2 if 1080 <= short <= 1440 else (
                    1 if 720 <= short <= 1440 else 0)
                try:
                    size = int(f.get("file_size") or f.get("size") or 0)
                except (ValueError, TypeError):
                    size = 0
                under_budget = size == 0 or size <= 175 * 1024 * 1024
                return (bool(native_hd) and under_budget, native_hd,
                        -abs(short - 1080), -(size or 0))
            return (short >= 1080, short, w * h)
        return max(files, key=score)

    def _coverr_budget(self):
        # Shared Free plan: 50 requests/hour. Limit calls per job to avoid
        # consuming the entire quota in a ten-video GitHub Actions run.
        try:
            cap = int(os.environ.get("PURFFLE_COVERR_MAX_CALLS", "5"))
        except ValueError:
            cap = 5
        cap = max(0, min(10, cap))
        if self._coverr_requests >= cap:
            raise ProviderError("quota_budget", "Coverr free API per-job budget reached")
        self._coverr_requests += 1

    @staticmethod
    def _coverr_download_url(value):
        if not secure_url(value):
            return False
        try:
            u = urlparse(value)
            return (u.hostname in ("storage.coverr.co", "cdn.coverr.co")
                    and u.port in (None, 443) and not u.fragment
                    and u.path.startswith("/videos/")
                    and not re.search(r"preview|thumbnail|watermark", u.path, re.I))
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _coverr_key():
        # COVER2 is a compatibility alias only if the original key is absent.
        # Never switch keys after a 401/429 or to bypass Coverr rate limits.
        return (os.environ.get("COVERR_API_KEY", "").strip()
                or os.environ.get("COVER2", "").strip())

    def _coverr(self, query):
        """Free API: original filmed clips only; reject unknown origin."""
        self._coverr_budget()
        data = self.client.get("https://api.coverr.co/videos",
            params={"query": query[:90], "page": 0, "page_size": 12,
                    "urls": "true", "filter": "is_ai_generated:false"},
            headers={"x-api-key": self._coverr_key()})
        hits = data.get("hits", [])
        if not isinstance(hits, list):
            raise ProviderError("invalid_schema", "Coverr hits list missing")
        result = []
        for rank, clip in enumerate(hits[:12]):
            if not isinstance(clip, dict) or clip.get("is_ai_generated") is not False:
                continue
            if any(clip.get(k) for k in (
                    "is_sponsored", "sponsored", "sponsored_by", "partner",
                    "is_premium", "premium", "watermarked", "is_watermarked")):
                continue
            if str(clip.get("access_tier", "free")).lower() not in ("free", "demo", "stock", ""):
                continue
            if str(clip.get("source", "coverr")).lower() not in ("coverr", ""):
                continue
            urls = clip.get("urls") or {}
            if not isinstance(urls, dict):
                continue
            video = urls.get("mp4") or ""
            if not self._coverr_download_url(video):
                continue
            identifier = str(clip.get("id") or "")
            if not re.fullmatch(r"[A-Za-z0-9_-]{3,64}", identifier):
                continue
            title = clean(clip.get("title"))
            if not title:
                continue
            slug = str(clip.get("slug") or "")
            page = str(clip.get("url") or "")
            if not (secure_url(page) and urlparse(page).hostname in
                    ("coverr.co", "www.coverr.co")):
                page = ("https://coverr.co/videos/" + slug
                        if re.fullmatch(r"[a-z0-9-]{4,140}", slug)
                        else "https://coverr.co/")
            person = clip.get("creator") or clip.get("contributor") or {}
            if isinstance(person, dict):
                creator = clean(person.get("name") or person.get("username"))
                profile = str(person.get("url") or person.get("profile_url") or "")
            else:
                creator, profile = clean(person), ""
            creator = creator or "Coverr contributor"
            if not (secure_url(profile) and urlparse(profile).hostname in
                    ("coverr.co", "www.coverr.co")):
                profile = "https://coverr.co/"
            lic = self.license("COVERR", LicenseValidator.STOCK["COVERR"],
                               creator, page)
            lic["attribution_required"] = True
            lic["attribution"] = (
                f"Video by {creator} on Coverr ({profile}) | "
                f"https://coverr.co/ | Source: {page} | Cropped/trimmed")
            details = clean([title, clip.get("description"), clip.get("tags")])
            try:
                width = int(clip.get("max_width") or clip.get("width") or 0)
                height = int(clip.get("max_height") or clip.get("height") or 0)
                duration = float(clip.get("duration") or 0)
            except (TypeError, ValueError):
                continue
            if width and height and min(width, height) < 720:
                continue
            item = self._item("coverr-video", identifier, video, query, rank,
                              details, lic, width, height, duration)
            if item is not None:
                item.extra["coverr_original_stock"] = True
                item.extra["coverr_download_tracking_required"] = True
                item.extra["signed_download_url_private"] = True
                result.append(item)
        return sorted(result, key=lambda x:
                      (x.height > x.width, min(x.width, x.height)), reverse=True)

    def track_download(self, item):
        """Mandatory Nov 2026 Coverr download reporting before acceptance."""
        if item.source != "coverr-video":
            return
        if (not item.extra.get("coverr_original_stock") or
                not item.extra.get("coverr_download_tracking_required") or
                not re.fullmatch(r"[A-Za-z0-9_-]{3,64}", item.id)):
            raise ProviderError("license_blocked", "Coverr free stock provenance missing")
        self._coverr_budget()
        self.client.patch(
            "https://api.coverr.co/videos/" + item.id + "/stats/downloads",
            headers={"x-api-key": self._coverr_key()})


    @staticmethod
    def _nps_public_domain_credit(credit, record):
        """NPS PD rule: official NPS credit without copyright marking.

        NPS expressly warns that third-party / copyright-credited assets
        are NOT necessarily public domain. Reject missing/ambiguous credits.
        """
        text = clean(credit).strip()
        if not text or re.search(
                r"©|\u00a9|\(c\)|copyright|courtesy|permission|"
                r"licensed|third.party|contractor|partner|Getty|Shutterstock",
                text, re.I):
            return False
        if not (re.fullmatch(r"NPS(?: Video)?|National Park Service", text, re.I)
                or re.fullmatch(r"NPS\s*/\s*[A-Za-z][A-Za-z .'-]{1,80}", text)):
            return False
        rights = clean([record.get("copyright"), record.get("rights"),
                        record.get("license"), record.get("usage")]).strip()
        return not rights or (
            bool(re.search(r"public domain|no copyright", rights, re.I))
            and not re.search(r"©|all rights reserved|permissions required",
                              rights, re.I))

    def _nps(self, query):
        """Official NPS multimedia/videos API, real downloadable MP4 only.

        NPS documents public-domain status for NPS-credited works without
        copyright symbols. No third-party, uncredited or unclear assets.
        Real pixels, crop, motion and scene match are checked downstream.
        """
        data = self.client.get("https://developer.nps.gov/api/v1/multimedia/videos",
            params={"q": query[:100], "limit": 16, "start": 0},
            headers={"X-Api-Key": os.environ["NPS_API_KEY"]})
        records = data.get("data")
        if not isinstance(records, list):
            raise ProviderError("invalid_schema", "NPS video data list missing")
        result = []
        for rank, row in enumerate(records[:16]):
            if not isinstance(row, dict):
                continue
            if not self._nps_public_domain_credit(row.get("credit"), row):
                continue
            # Prefer unscored raw footage to documentaries with third-party
            # footage, music and talent rights mixed into the final edit.
            if row.get("isBRoll") is not True and row.get("isVideoOnly") is not True:
                continue
            identity = str(row.get("id") or "").strip()
            if not re.fullmatch(
                    r"[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}",
                    identity):
                continue
            page = str(row.get("permalinkUrl") or "").strip()
            try:
                parsed = urlparse(page)
                page_ok = (parsed.scheme == "https"
                           and parsed.hostname in ("www.nps.gov", "nps.gov")
                           and parsed.path == "/media/video/view.htm"
                           and parse_qs(parsed.query).get("id", [""])[0].lower()
                               == identity.lower())
            except (ValueError, TypeError):
                page_ok = False
            if not page_ok:
                continue
            versions = row.get("versions")
            if not isinstance(versions, list):
                continue
            candidates = []
            for variant in versions:
                if not isinstance(variant, dict):
                    continue
                url = str(variant.get("url") or "")
                try:
                    loc = urlparse(url)
                    width = int(variant.get("widthPixels") or 0)
                    height = int(variant.get("heightPixels") or 0)
                except (ValueError, TypeError):
                    continue
                if (loc.scheme != "https"
                        or loc.hostname not in ("www.nps.gov", "nps.gov")
                        or not loc.path.startswith("/nps-audiovideo/audiovideo/")
                        or not video_url(url)
                        or not loc.path.lower().endswith(".mp4")
                        or str(variant.get("fileType") or "").lower() != "video/mp4"
                        or min(width, height) < 720):
                    continue
                candidates.append((width * height, width, height, url))
            if not candidates:
                continue
            _, width, height, url = max(candidates)
            lic = self.license(
                "PDM-1.0",
                "https://creativecommons.org/publicdomain/mark/1.0/",
                row.get("credit"), page)
            lic["rights_basis"] = "NPS-only credit, no copyright mark"
            lic["attribution_required"] = False
            try:
                duration = max(0.0, float(row.get("durationMs") or 0) / 1000)
            except (TypeError, ValueError):
                continue
            item = self._item("nps-video", identity, url, query, rank,
                              clean([row.get("title"), row.get("description"),
                                     row.get("descriptiveTranscript"),
                                     row.get("tags")])[:3500],
                              lic, width, height,
                              duration)
            if item:
                result.append(item)
        return result

    def _freenaturestock(self, query):
        """Search a finite manually verified CC0 video manifest, not the website.

        Site terms prohibit spidering/crawling/scraping. This adapter never
        requests HTML, feeds, search endpoints or sitemaps. It offers *only*
        official static MP4 download links already in our reviewed manifest.
        The shared VideoDownloader still performs HTTPS/SSRF, size, FFprobe,
        native 720p crop, motion, license, duplicate and local CLIP checks.
        """
        manifest_path = (Path(__file__).resolve().parent.parent /
                         "data" / "freenaturestock_video_catalog.json")
        try:
            catalog = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ProviderError("catalog_invalid", "Curated nature-video manifest missing or malformed") from exc
        if (catalog.get("license_id") != "CC0-1.0" or
                catalog.get("license_url") != "https://creativecommons.org/publicdomain/zero/1.0/" or
                not isinstance(catalog.get("clips"), list)):
            raise ProviderError("catalog_invalid", "Unapproved stock license or missing clip manifest")
        stop = {"the", "and", "with", "from", "for", "into", "over",
                "under", "video", "videos", "footage", "nature", "stock",
                "close", "up", "camera", "cinematic", "ambient"}
        def tokens(text):
            words = re.findall(r"[a-z0-9]+", str(text).casefold())
            return {w[:-1] if w.endswith("s") and len(w) > 4
                    else w for w in words if len(w) >= 3 and w not in stop}
        requested = tokens(query)
        if not requested:
            return []
        results = []
        for row in catalog["clips"][:120]:
            if not isinstance(row, dict):
                continue
            title = str(row.get("title", ""))
            match = len(requested & tokens(title))
            if not match:
                continue  # no random scenery to fill a science scene
            video = str(row.get("video_url", ""))
            page = str(row.get("source_page", ""))
            u, p = urlparse(video), urlparse(page)
            if (u.scheme != "https" or u.hostname != "cdn.freenaturestock.com"
                    or not re.fullmatch(r"/videos/freenaturestock-[a-z0-9-]+\.mp4", u.path)
                    or u.query or u.fragment or u.username or u.password
                    or p.scheme != "https" or p.hostname != "freenaturestock.com"
                    or not re.fullmatch(r"/video/[a-z0-9-]+/", p.path)
                    or p.query or p.fragment or not title or len(title) > 140):
                continue
            try:
                width, height = int(row["width"]), int(row["height"])
                duration = float(row["duration"])
            except (TypeError, KeyError, ValueError):
                continue
            if min(width, height) < 720 or not 3 <= duration <= 300:
                continue
            license_info = self.license(
                "CC0-1.0", "https://creativecommons.org/publicdomain/zero/1.0/",
                "Free Nature Stock", page)
            item = self._item(
                "freenaturestock-video", row.get("id", title),
                video, query, 0, title, license_info,
                width, height, duration)
            if item is not None:
                item.extra["catalog_mode"] = "manually_verified_official_downloads_no_crawl"
                item.extra["catalog_match_terms"] = match
                results.append((match, item))
        results.sort(key=lambda pair: (-pair[0], -min(pair[1].width, pair[1].height),
                                        pair[1].id))
        return [item for _, item in results]

    def _pixabay(self, query):
        # One API request now screens up to 60 candidates rather than 20.
        # No extra provider calls; downloaded clips remain strictly bounded
        # by time, quality, relevance, real-footage and license checks.
        data = self.client.get("https://pixabay.com/api/videos/", params={
            "key": os.environ["PIXABAY_API_KEY"], "q": query[:100], "per_page": 60,
            "safesearch": "true", "video_type": "film"})
        result = []
        for rank, x in enumerate(data.get("hits", [])):
            f = self._files((x.get("videos") or {}).values())
            if not f:
                continue
            lic = self.license("PIXABAY", LicenseValidator.STOCK["PIXABAY"], x.get("user") or "Pixabay contributor", x.get("pageURL", ""))
            item = self._item("pixabay", x["id"], f["url"], query, rank, x.get("tags"), lic,
                              f.get("width"), f.get("height"), x.get("duration"))
            if item:
                result.append(item)
        # Portrait helps only after metadata relevance and license are validated downstream.
        return sorted(result, key=lambda x: (x.height > x.width, min(x.width, x.height)), reverse=True)

    def _pexels(self, query):
        # One API request now screens up to 50 candidates rather than 15.
        # The documented per_page maximum is 80; do not increase requests.
        # Pexels documents /v1/videos/; the legacy /videos/ path is
        # deprecated. Search both orientations: 4K landscape clips can make
        # verified vertical 720p crops, and portrait is still ranked first.
        data = self.client.get("https://api.pexels.com/v1/videos/search", params={
            "query": query, "per_page": 50, "size": "large"},
            headers={"Authorization": os.environ["PEXELS_API_KEY"]})
        result = []
        for rank, x in enumerate(data.get("videos", [])):
            f = self._files(x.get("video_files", []), "link")
            if not f:
                continue
            page = x.get("url", "")
            slug = re.sub(r"[-_\d]+", " ", page.rstrip("/").split("/")[-1])
            lic = self.license("PEXELS", LicenseValidator.STOCK["PEXELS"], (x.get("user") or {}).get("name") or "Pexels contributor", page)
            item = self._item("pexels", x["id"], f["link"], query, rank,
                              slug + " " + clean(x.get("tags")), lic, f.get("width"), f.get("height"), x.get("duration"))
            if item:
                result.append(item)
        return sorted(result, key=lambda x: (x.height > x.width, min(x.width, x.height)), reverse=True)

    def _wikimedia(self, query):
        data = self.client.get(API, params={"action": "query", "generator": "search",
            "gsrsearch": query + " filetype:video", "gsrnamespace": 6, "gsrlimit": 15,
            "prop": "imageinfo", "iiprop": "url|size|mime|extmetadata", "format": "json", "maxlag": 5})
        if "error" in data:
            raise ProviderError("api_error", clean(data["error"].get("code")))
        result = []
        for rank, page in enumerate(data.get("query", {}).get("pages", {}).values()):
            info = (page.get("imageinfo") or [{}])[0]
            if info.get("mime") not in VIDEO_MIMES:
                continue
            ext = info.get("extmetadata", {})
            get = lambda k: clean((ext.get(k) or {}).get("value"))
            url = get("LicenseUrl")
            lid = LicenseValidator.identify(url, get("LicenseShortName"))
            # Commons PD records often have no LicenseUrl; their metadata has an explicit UsageTerms.
            if not lid and get("LicenseShortName").lower() in {"public domain", "cc0"}:
                url = "https://creativecommons.org/publicdomain/" + ("zero/1.0/" if get("LicenseShortName").lower() == "cc0" else "mark/1.0/")
                lid = LicenseValidator.identify(url)
            lic = self.license(lid, url, get("Artist"), info.get("descriptionurl", ""))
            item = self._item("wikimedia-video", page["pageid"], info.get("url", ""), query, rank,
                              page.get("title", "").replace("File:", "").replace("_", " ") + " " + get("ImageDescription"),
                              lic, info.get("width"), info.get("height"))
            if item:
                result.append(item)
        return result

    def _nasa(self, query):
        data = self.client.get("https://images-api.nasa.gov/search", params={
            "q": query, "media_type": "video", "page_size": 8})
        result = []
        for rank, entry in enumerate(data.get("collection", {}).get("items", [])):
            meta = (entry.get("data") or [{}])[0]
            identifier = meta.get("nasa_id")
            if not identifier or meta.get("media_type") != "video":
                continue
            rights_text = clean([meta.get("description"), meta.get("secondary_creator"), meta.get("photographer"), meta.get("copyright")])
            # NASA's collection includes partner material. Reject explicit outside credits rather
            # than applying the agency policy to third-party copyrighted footage.
            if re.search(r"copyright|©|all rights reserved|courtesy|getty|shutterstock|reuters|associated press|esa[/ ,]|spacex", rights_text, re.I):
                continue
            credit_fields = [clean(meta.get(k)) for k in ("secondary_creator", "photographer") if meta.get(k)]
            if any(not re.search(r"\bNASA\b|\bJPL\b|Goddard|Johnson Space Center|Kennedy Space Center", c, re.I)
                   for c in credit_fields):
                continue
            manifest = self.client.get("https://images-api.nasa.gov/asset/" + quote(str(identifier), safe=""))
            links = [x.get("href", "") for x in manifest.get("collection", {}).get("items", [])]
            # Official manifests still emit HTTP assets. The same NASA CDN path is
            # available over TLS; upgrade only the NASA-owned asset hostname.
            links = [u.replace("http://", "https://", 1)
                     if urlparse(u).hostname == "images-assets.nasa.gov" and u.startswith("http://") else u
                     for u in links]
            candidates = [u for u in links if secure_url(u) and re.search(r"\.mp4(?:[?#]|$)", u, re.I)
                          and not re.search(r"~(?:small|mobile|preview)", u, re.I)]
            if not candidates:
                continue
            # NASA manifest naming: orig > large > medium. Never invent width or height.
            def quality(u):
                return 3 if "~orig" in u.lower() else 2 if "~large" in u.lower() else 1 if "~medium" in u.lower() else 0
            url = max(candidates, key=quality)
            page = "https://images.nasa.gov/details/" + quote(str(identifier), safe="")
            creator = meta.get("secondary_creator") or ("NASA " + clean(meta.get("center")))
            lic = self.license("NASA-MEDIA", NASA_POLICY, creator, page)
            item = self._item("nasa-video", identifier, url, query, rank,
                              clean([meta.get("title"), meta.get("keywords"), meta.get("description")]), lic)
            if item:
                result.append(item)
        return result

    def _archive(self, query):
        # Quote scene terms so a user/topic cannot inject Archive query operators.
        terms = " ".join(re.findall(r"[A-Za-z0-9]+", query))
        data = self.client.get("https://archive.org/advancedsearch.php", params={
            "q": f'mediatype:movies AND ("{terms}") AND (licenseurl:"https://creativecommons.org/publicdomain/zero/1.0/" OR licenseurl:"http://creativecommons.org/publicdomain/zero/1.0/" OR licenseurl:"https://creativecommons.org/publicdomain/mark/1.0/" OR licenseurl:"http://creativecommons.org/publicdomain/mark/1.0/")',
            "fl[]": ["identifier", "title", "licenseurl"], "rows": 8, "output": "json"})
        result = []
        for rank, doc in enumerate(data.get("response", {}).get("docs", [])):
            identifier = doc.get("identifier")
            if not identifier:
                continue
            meta = self.client.get("https://archive.org/metadata/" + quote(identifier, safe=""))
            md = meta.get("metadata", {})
            licenses = sequence(md.get("licenseurl"))
            if not licenses or any(LicenseValidator.identify(u) not in {"CC0-1.0", "PDM-1.0"} for u in licenses):
                continue
            files = [f for f in meta.get("files", []) if video_url("https://archive.org/" + f.get("name", ""))
                     and not re.search(r"thumb|preview|sample", f.get("name", ""), re.I)
                     and int(f.get("size") or 0) <= 300 * 1024 * 1024]
            if not files:
                continue
            # Prefer dimensions where known, originals then file size; ffprobe remains decisive.
            file = max(files, key=lambda f: (min(int(f.get("width") or 0), int(f.get("height") or 0)),
                       f.get("source") == "original", int(f.get("size") or 0)))
            url = "https://archive.org/download/" + quote(identifier, safe="") + "/" + quote(file["name"], safe="/")
            lic = self.license(LicenseValidator.identify(licenses[0]), licenses[0].replace("http://", "https://", 1),
                               md.get("creator"), "https://archive.org/details/" + quote(identifier, safe=""))
            item = self._item("archive-video", identifier, url, query, rank,
                              clean([md.get("title"), md.get("description"), md.get("subject")]), lic,
                              file.get("width"), file.get("height"))
            if item:
                result.append(item)
        return result

    def _europeana(self, query):
        data = self.client.get("https://api.europeana.eu/record/v2/search.json", params={
            "query": query, "qf": "TYPE:VIDEO", "media": "true", "reusability": "open",
            "rows": 30, "profile": "rich"}, headers={"X-Api-Key": os.environ["EUROPEANA_API_KEY"]})
        if data.get("success") is False:
            raise ProviderError("api_error", "Europeana rejected request")
        result = []
        for rank, entry in enumerate(data.get("items", [])):
            rights = sequence(entry.get("rights"))
            # Search rights are aggregated. Accept only consistently PD/CC0 records; no
            # claim that one permissive right grants rights to every linked representation.
            if str(entry.get("type", "")).upper() != "VIDEO" or not rights:
                continue
            if any(LicenseValidator.identify(r) not in {"CC0-1.0", "PDM-1.0"} for r in rights):
                continue
            urls = sequence(entry.get("edmIsShownBy")) + sequence(entry.get("edmHasView"))
            for url in urls:
                if not video_url(url):
                    continue
                lic = self.license(LicenseValidator.identify(rights[0]), rights[0].replace("http://", "https://", 1),
                                   entry.get("dcCreator") or entry.get("dataProvider"), entry.get("guid", ""))
                item = self._item("europeana-video", entry.get("id", rank), url, query, rank,
                                  clean([entry.get("title"), entry.get("dcDescription")]), lic)
                if item:
                    result.append(item)
                break
        return result


# Compatibility functions for callers of the original extension module.
def _compat(source, query, MediaItem):
    return ProviderRegistry(MediaItem).search(source, query)


def search_wikimedia_videos(query, MediaItem):
    return _compat("wikimedia-video", query, MediaItem)


def search_nasa_videos(query, MediaItem):
    return _compat("nasa-video", query, MediaItem)


def search_coverr_videos(query, MediaItem):
    return _compat("coverr-video", query, MediaItem)


def search_archive_videos(query, MediaItem):
    return _compat("archive-video", query, MediaItem)


def search_europeana_videos(query, MediaItem):
    return _compat("europeana-video", query, MediaItem)
