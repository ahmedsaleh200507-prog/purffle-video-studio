"""Search openly licensed moving footage from Wikimedia Commons."""
import re
import requests

API = "https://commons.wikimedia.org/w/api.php"
HEADERS = {"User-Agent":"PurffleVideoStudio/1.0 (https://github.com/ahmedsaleh200507-prog/purffle-video-studio)"}

def search_wikimedia_videos(query, MediaItem):
    try:
        response = requests.get(API, params={
            "action":"query", "generator":"search",
            "gsrsearch":query+" filetype:video", "gsrnamespace":6,
            "gsrlimit":20, "prop":"imageinfo",
            "iiprop":"url|size|mime|extmetadata", "format":"json"
        }, headers=HEADERS, timeout=18)
        response.raise_for_status()
        items = []
        for rank, page in enumerate(response.json().get("query",{}).get("pages",{}).values()):
            info = (page.get("imageinfo") or [{}])[0]
            mime = info.get("mime", "")
            url = info.get("url", "")
            if mime not in ("video/webm", "video/ogg", "video/mp4") or not url:
                continue
            lic = re.sub("<[^>]+>", "", (info.get("extmetadata",{}).get("LicenseShortName",{}).get("value") or "")).lower().strip()
            if not (lic.startswith("cc by") or lic in ("cc0","public domain","pd")):
                continue
            items.append(MediaItem("wikimedia-video", str(page.get("pageid")), "video",
                url, int(info.get("width") or 0), int(info.get("height") or 0),
                credit=f"{lic} | {info.get('descriptionurl') or ''}",
                query=query, rank=rank, text=page.get("title","").replace("File:","").replace("_"," ")))
        return items
    except Exception as exc:
        print(f"Wikimedia video search unavailable: {exc}",flush=True)
        return []


def search_nasa_videos(query, MediaItem):
    """NASA video search with asset manifests; avoid image thumbnails."""
    try:
        data = requests.get("https://images-api.nasa.gov/search",
            params={"q":query,"media_type":"video","page_size":12},
            headers=HEADERS, timeout=18)
        data.raise_for_status()
        results = []
        for rank, entry in enumerate(data.json().get("collection",{}).get("items",[])):
            meta = (entry.get("data") or [{}])[0]
            nasa_id = meta.get("nasa_id")
            if not nasa_id:
                continue
            manifest = requests.get("https://images-api.nasa.gov/asset/"+requests.utils.quote(str(nasa_id),safe=""),
                headers=HEADERS,timeout=15)
            manifest.raise_for_status()
            links = [x.get("href","") for x in manifest.json().get("collection",{}).get("items",[])]
            candidates = [u for u in links if re.search(r"\.mp4(?:[?#]|$)",u,re.I)]
            if not candidates:
                continue
            url = next((u for u in candidates if "~small" in u.lower() or "~mobile" in u.lower()), candidates[-1])
            results.append(MediaItem("nasa-video",str(nasa_id),"video",url,1280,720,
                credit="NASA | "+str(entry.get("href") or ""),query=query,rank=rank,
                text=(meta.get("title") or "")+" "+" ".join(meta.get("keywords") or [])))
        return results
    except Exception as exc:
        print(f"NASA video search unavailable: {exc}",flush=True)
        return []


def search_coverr_videos(query, MediaItem):
    """Coverr API, enabled only when the user supplies a key."""
    import os
    key = os.environ.get("COVERR_API_KEY", "").strip()
    if not key:
        return []
    try:
        response = requests.get("https://api.coverr.co/videos",
            params={"query":query,"page_size":12,"urls":"true"},
            headers={**HEADERS,"x-api-key":key},timeout=18)
        response.raise_for_status()
        results=[]
        for rank, entry in enumerate(response.json().get("hits", [])):
            urls=entry.get("urls") or {}
            url=urls.get("mp4") or urls.get("mp4_download")
            if not url or not url.startswith("https://"):
                continue
            results.append(MediaItem("coverr-video",str(entry.get("id")),"video",url,
                int(entry.get("width") or 0),int(entry.get("height") or 0),
                credit="Coverr | https://coverr.co",query=query,rank=rank,
                text=entry.get("title") or ""))
        return results
    except Exception as exc:
        print(f"Coverr video search unavailable: {exc}",flush=True)
        return []


def search_archive_videos(query, MediaItem):
    """Only explicitly CC0/public-domain items, never arbitrary archive uploads."""
    from urllib.parse import quote
    try:
        search = requests.get("https://archive.org/advancedsearch.php",
            params={"q":f'mediatype:movies AND ({query}) AND (licenseurl:*creativecommons.org/publicdomain/zero* OR licenseurl:*creativecommons.org/publicdomain/mark*)',
                    "fl[]":["identifier","title","licenseurl"],"rows":8,"output":"json"},
            headers=HEADERS,timeout=18)
        search.raise_for_status()
        results=[]
        for rank, doc in enumerate(search.json().get("response",{}).get("docs",[])):
            identifier=doc.get("identifier","")
            license_url=str(doc.get("licenseurl") or "").lower()
            if not identifier or not ("publicdomain/zero" in license_url or "publicdomain/mark" in license_url):
                continue
            metadata=requests.get("https://archive.org/metadata/"+quote(identifier,safe=""),headers=HEADERS,timeout=15)
            metadata.raise_for_status()
            files=metadata.json().get("files") or []
            video=next((f for f in files if str(f.get("name","")).lower().endswith(".mp4") and
                        not any(w in str(f.get("name","")).lower() for w in ("thumb","preview","sample"))),None)
            if not video:
                continue
            url="https://archive.org/download/"+quote(identifier,safe="")+"/"+quote(video["name"],safe="/")
            results.append(MediaItem("archive-video",identifier,"video",url,
                credit=f"Internet Archive | {license_url} | https://archive.org/details/{identifier}",
                query=query,rank=rank,text=doc.get("title") or ""))
        return results
    except Exception as exc:
        print(f"Internet Archive video search unavailable: {exc}",flush=True)
        return []


def search_europeana_videos(query, MediaItem):
    """Europeana Search API: public-domain direct MP4 only, never thumbnails."""
    import os
    key = os.environ.get("EUROPEANA_API_KEY", "").strip()
    if not key:
        print("[SOURCE CHECK] Europeana skipped: EUROPEANA_API_KEY not set", flush=True)
        return []
    try:
        response = requests.get(
            "https://api.europeana.eu/record/v2/search.json",
            params={"query":query, "qf":"TYPE:VIDEO", "media":"true",
                    "reusability":"open", "rows":30, "profile":"rich"},
            headers={**HEADERS, "X-Api-Key":key}, timeout=18)
        response.raise_for_status()
        results = []
        for rank, entry in enumerate(response.json().get("items", [])):
            if str(entry.get("type", "")).upper() != "VIDEO":
                continue
            rights = entry.get("rights") or []
            if isinstance(rights, str):
                rights = [rights]
            # Avoid licenses requiring attribution/share-alike handling until
            # a proper video credits manifest is implemented.
            if not any("publicdomain/zero/" in str(x).lower() or
                       "publicdomain/mark/" in str(x).lower()
                       for x in rights):
                continue
            urls = entry.get("edmIsShownBy") or []
            if isinstance(urls, str):
                urls = [urls]
            urls += entry.get("edmHasView") or []
            for url in urls:
                if not isinstance(url, str) or not url.startswith("https://"):
                    continue
                if not re.search(r"\.mp4(?:[?#]|$)", url, re.I):
                    continue
                title = entry.get("title") or []
                if isinstance(title, list):
                    title = " ".join(str(x) for x in title)
                results.append(MediaItem(
                    "europeana-video", str(entry.get("id") or rank), "video",
                    url, 0, 0, credit="Europeana | "+str(entry.get("guid") or ""),
                    query=query, rank=rank, text=title))
                break
        return results
    except Exception as exc:
        print(f"Europeana video search unavailable: {exc}", flush=True)
        return []
