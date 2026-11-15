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
