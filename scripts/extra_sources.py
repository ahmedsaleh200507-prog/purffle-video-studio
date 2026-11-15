"""Public, API-backed visual sources. Conservative licenses and metadata."""
import re
from urllib.parse import quote
import requests

UA = {"User-Agent": "PurffleVideoStudio/1.0 (educational video maker; https://github.com/ahmedsaleh200507-prog/purffle-video-studio)"}
ALLOWED = {"cc0", "pdm", "by", "by-sa", "cc-by", "cc-by-sa", "public domain"}

def _get(url, params):
    response = requests.get(url, params=params, headers=UA, timeout=18)
    response.raise_for_status()
    return response.json()

def search(source, query, MediaItem):
    result = []
    try:
        if source == "openverse":
            data = _get("https://api.openverse.org/v1/images/", {"q": query, "page_size": 15, "license_type": "commercial,modification"})
            for rank, x in enumerate(data.get("results", [])):
                license_name = (x.get("license") or "").lower()
                if license_name not in ALLOWED or not x.get("url"):
                    continue
                url = x["url"]
                if not re.search(r"\\.(jpg|jpeg|png|webp)(?:[?#]|$)", url, re.I):
                    continue
                title = x.get("title") or ""
                result.append(MediaItem("openverse", str(x.get("id")), "image", url, int(x.get("width") or 0), int(x.get("height") or 0), credit=f"{x.get('creator') or 'Unknown'} | {license_name} | {x.get('foreign_landing_url') or ''}", query=query, rank=rank, text=title))
        elif source == "wikimedia":
            data = _get("https://commons.wikimedia.org/w/api.php", {"action":"query","generator":"search","gsrsearch":query+" filetype:bitmap","gsrnamespace":6,"gsrlimit":15,"prop":"imageinfo","iiprop":"url|size|mime|extmetadata","format":"json"})
            for rank, page in enumerate(data.get("query", {}).get("pages", {}).values()):
                info = (page.get("imageinfo") or [{}])[0]
                metadata = info.get("extmetadata") or {}
                lic = re.sub("<[^>]+>", "", (metadata.get("LicenseShortName") or {}).get("value", "")).strip().lower()
                if not (lic in ALLOWED or lic.startswith("cc by") or lic.startswith("cc0")):
                    continue
                url = info.get("url", "")
                if info.get("mime") not in ("image/jpeg", "image/png") or not url:
                    continue
                result.append(MediaItem("wikimedia", str(page.get("pageid")), "image", url, int(info.get("width") or 0), int(info.get("height") or 0), credit=f"{lic} | {info.get('descriptionurl') or ''}", query=query, rank=rank, text=page.get("title", "").replace("File:", "").replace("_", " ")))
        elif source == "nasa":
            data = _get("https://images-api.nasa.gov/search", {"q":query, "media_type":"image", "page_size":15})
            for rank, entry in enumerate(data.get("collection", {}).get("items", [])):
                metadata = (entry.get("data") or [{}])[0]
                if (metadata.get("center") or "").upper() not in ("", "NASA", "JPL"):
                    continue
                links = entry.get("links") or []
                thumb = next((x.get("href") for x in links if x.get("render") == "image"), None)
                if not thumb:
                    continue
                result.append(MediaItem("nasa", str(metadata.get("nasa_id") or rank), "image", thumb, 1280, 720, credit=f"NASA | {entry.get('href', '')}", query=query, rank=rank, text=(metadata.get("title") or "")+" "+(metadata.get("description") or "")[:200]))
    except Exception as exc:
        print(f"Visual source {source} unavailable: {exc}", flush=True)
    return result
