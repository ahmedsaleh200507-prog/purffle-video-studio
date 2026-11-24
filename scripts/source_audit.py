"""Independent bounded source audit; no narration, paid inference or publishing."""
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
from video_sources import ProviderRegistry, JsonClient, PROVIDERS, LicenseValidator, STATIC_CATALOGS
from media_validation import VideoDownloader, QualityValidator, portrait_crop_allowed, download_hd_variant
from portrait_layout import plan_portrait, render_context

QUERIES = {
    "pixabay": ["ocean waves", "forest", "volcano"],
    "pexels": ["ocean waves", "forest", "volcano"],
    "wikimedia-video": ["volcano eruption", "ocean waves", "forest"],
    "nasa-video": ["sun solar activity", "earth from space", "moon"],
    "archive-video": ["volcano", "nature", "historic film"],
    "europeana-video": ["historic film", "train", "city"],
    "nps-video": ["Yellowstone", "geyser", "waterfall", "bison", "wildlife", "national park"],
    "usgs-video": ["lava", "volcano eruption", "Kilauea"],
    "freenaturestock-video": ["ocean waves", "forest", "clouds"],
    "coverr-video": ["ocean waves", "forest"],
}

def safe_error(exc):
    msg = str(exc).splitlines()[0][:180] if str(exc) else type(exc).__name__
    msg = re.sub(r"https?://\S+", "[url omitted]", msg)
    return type(exc).__name__ + ": " + msg

def audit(provider):
    row = {"provider": provider.name, "mode": "static_catalog" if provider.name in STATIC_CATALOGS else "api",
           "key_present": (bool(os.environ.get(provider.key_env, "").strip() or
                                (provider.alternate_key_env and os.environ.get(provider.alternate_key_env, "").strip()))
                           if provider.key_env else None),
           "queries": [], "downloads": [], "status": "not_tested"}
    reason = provider.unavailable_reason()
    if reason:
        row.update(status="policy_blocked" if provider.policy_block else "missing_key", reason=reason)
        return row
    with tempfile.TemporaryDirectory(prefix="source-audit-") as folder:
        root = Path(folder)
        reg = ProviderRegistry(MediaItem=lambda *args, **kwargs: SimpleNamespace(
            source=args[0], id=args[1], kind=args[2], url=args[3], width=args[4], height=args[5], extra={}, **kwargs),
            client=JsonClient(cache_dir=root/"api", ttl=0))
        dl = VideoDownloader(cache_dir=root/"video", max_bytes=175*1024*1024,
                             max_cache_bytes=1024**3, timeout=15, total_timeout=65)
        validator = QualityValidator(min_short_side=720)
        tested = set()
        # Coverr must not be downloaded or admitted to production without
        # satisfying its attribution and tracking requirements.
        if provider.name == "coverr-video":
            os_policy = os.environ.get("PURFFLE_NO_ATTRIBUTION")
            # Direct adapter call for this isolated diagnostic only; no global
            # environment mutation and no download or tracking.
            for query in QUERIES[provider.name]:
                try:
                    candidates = reg._coverr(query)
                    row["queries"].append({"query":query,"status":"ok" if candidates else "empty",
                                           "candidate_count":len(candidates)})
                except Exception as exc:
                    row["queries"].append({"query":query,"status":getattr(exc,"status","error"),
                                           "reason":type(exc).__name__})
            row.update(status="policy_blocked", reason="Coverr requires attribution; download not attempted",
                       search_returned_candidates=any(q.get("candidate_count",0)>0 for q in row["queries"]))
            return row
        for query in QUERIES.get(provider.name, ["ocean waves"]):
            try:
                candidates = reg.search(provider.name, query)
                event = reg.events[-1]
                row["queries"].append({"query":query,"status":event["status"],
                                      "candidate_count":len(candidates),"reason":event["detail"]})
            except Exception as exc:
                row["queries"].append({"query":query,"status":"error","reason":type(exc).__name__})
                continue
            for item in candidates:
                if item.id in tested or len(row["downloads"]) >= 4:
                    continue
                tested.add(item.id)
                item_license = item.extra.get("license", {})
                attempt = {"id":item.id,"license":item_license.get("id"),
                           "attribution_required":bool(item_license.get("attribution_required"))}
                try:
                    if not LicenseValidator.validate(item_license) or attempt["attribution_required"]:
                        raise ValueError("license rejected by no-attribution policy")
                    path, quality = download_hd_variant(item, dl, validator, segment_seconds=15)
                    attempt["downloaded"] = True
                    attempt["download_evidence"] = item.extra.get("download_evidence", {})
                    attempt["partial_attempts"] = item.extra.get("partial_attempts", [])
                    w,h = quality["width"],quality["height"]
                    scale = max(1080/min(w,h*9/16),1920/h)
                    layout=plan_portrait(w,h,1080,1920)
                    context_ok=False
                    context_reason=None
                    if layout and layout["mode"]=="full_frame_context":
                        try:
                            context_path=render_context(path,layout,min(5.,float(quality["duration"])))
                            composed=validator.validate(context_path)
                            context_ok=(composed["width"],composed["height"])==(1080,1920)
                        except Exception as exc:
                            context_reason=safe_error(exc)
                    attempt.update(status="hd_motion_ok",width=w,height=h,
                                   seconds=round(quality["duration"],2),fps=quality["fps"],
                                   motion_mode=quality.get("motion_mode","standard"),
                                   localized_motion=quality.get("localized_motion"),
                                   long_hd_ok=w>=1280 and h>=720,
                                   shorts_crop_ok=portrait_crop_allowed(scale),
                                   shorts_context_ok=context_ok,shorts_context_reason=context_reason,
                                   shorts_layout=layout,shorts_1080_output_ok=portrait_crop_allowed(scale) or context_ok)
                    row["downloads"].append(attempt)
                    row.update(status="verified_hd_download",reason="Licensed moving HD sample downloaded and decoded")
                    return row
                except Exception as exc:
                    attempt.update(status="rejected",reason=safe_error(exc),
                                   partial_attempts=item.extra.get("partial_attempts", []))
                    row["downloads"].append(attempt)
            if row["queries"][-1]["status"] in ("http_401","http_403","http_429","circuit_open"):
                break
        if row["downloads"]:
            row.update(status="download_or_quality_failed",reason="Candidates found; none passed bounded download and HD motion test")
        elif any(q.get("status")=="empty" for q in row["queries"]):
            row.update(status="no_eligible_results",reason="No eligible results for sampled queries; not proof the provider is broken")
        else:
            row.update(status="search_failed",reason="See per-query statuses")
    return row

def main():
    out=Path("source-audit")
    out.mkdir(exist_ok=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows=list(pool.map(audit, PROVIDERS))
    (out/"report.json").write_text(json.dumps(rows,indent=2,ensure_ascii=False),encoding="utf-8")
    lines=["# Video source audit","","| Source | Status | Reason |","|---|---|---|"]
    for row in rows:
        lines.append("| "+row["provider"]+" | "+row["status"]+" | "+row.get("reason","").replace("|","/")+" |")
        print("[AUDIT]",row["provider"],row["status"],row.get("reason",""),flush=True)
    lines += ["","Tests use bounded sample queries. A pass does not establish relevance for every topic, copyright ownership, or YouTube monetization.",
              "See report.json for queries, download failures and HD dimensions."]
    summary="\n".join(lines)+"\n"
    (out/"summary.md").write_text(summary,encoding="utf-8")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"],"a",encoding="utf-8") as f: f.write(summary)

if __name__ == "__main__":
    main()
