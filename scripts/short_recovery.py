"""Recover a source-reviewed Shorts script with verified real footage/photos and locked Piper."""
import json
import os
import subprocess
import shutil
import time
from pathlib import Path
from types import SimpleNamespace

def save_reviewed_script(screenplay,language,topic,destination=None):
    dest=destination or os.environ.get("PURFFLE_REVIEWED_SCRIPT")
    if not dest:
        return
    from production_checkpoint import write
    scenes=[]
    for scene in screenplay.scenes:
        plan={k:str(getattr(scene,k,"") or "") for k in
              ("main_character","object","action","location","time","visual_search_query")}
        scenes.append({**plan,"narration":str(scene.narration),"visual_subject":plan["object"]})
    write(Path(dest),{"topic":topic,"language":language,"scenes":scenes,"reviewed":True})

def recover_approved_dossier(topic,language,target):
    """Zero text API calls for exact, previously source-reviewed subjects only."""
    from fact_checked_topics import verified_documentary_kind
    kind=verified_documentary_kind(topic)
    if not kind:
        raise RuntimeError("No source-reviewed offline script for this exact topic")
    from science_sources import discover_evidence,screen_narration
    from official_draft import approved_dossier_draft
    from studio_runtime import install
    install()
    evidence=discover_evidence(topic,language)
    if evidence.method!="curated_editor_reviewed":
        raise RuntimeError("No official fixed offline dossier")
    count=2 if kind in {"mirror_condensation","iceberg_breakup","whale_breaching",
                          "lightning_thunder_delay","ocean_glow_bioluminescence",
                          "northern_lights_glow"} else 3
    draft=approved_dossier_draft(topic,language,evidence,scene_count=count)
    if draft is None:
        raise RuntimeError("Offline approved draft unavailable")
    screenplay=draft[0]
    from science_fact_guard import validate_unsourced_quantities
    validate_unsourced_quantities(screenplay,topic)
    screen_narration(screenplay,evidence,None,path=target/"offline-science-report.json")
    save_reviewed_script(screenplay,language,topic,target/"reviewed-script.json")
    print("[ZERO API RECOVERY] Exact official dossier, fixed reviewed narration",flush=True)

def search_recovery_clip(visuals,scene,topic,index,need,work):
    from visual_director import build_contract
    data={k:str(scene.get(k) or "") for k in
          ("main_character","object","action","location","time","visual_search_query")}
    data["object"]=data["object"] or scene["visual_subject"]
    data["action"]=data["action"] or "ambient"
    contract=build_contract(SimpleNamespace(**data,narration=scene["narration"]),topic,index)
    data["visual_search_query"]=contract["queries"][0]
    data["_visual_contract"]=contract
    visuals._shot_deadline=time.monotonic()+90
    item=visuals.for_scene(index-1,data["visual_search_query"],json.dumps(data),topic,need,work)
    row=visuals.report["scenes"][-1]
    if row.get("status")!="selected" or not row.get("match",{}).get("director_check",{}).get("verified"):
        raise RuntimeError("Recovery clip lacks independent visual director proof")
    return Path(item.path),row

def run(args,timeout=240):
    subprocess.run(args,check=True,timeout=timeout,capture_output=True)

def recover_short(topic,language,target):
    target=Path(target).resolve()
    try:
        return _recover_short(topic,language,target)
    except Exception:
        (target/"review-video.mp4").unlink(missing_ok=True)
        raise
    finally:
        shutil.rmtree(target/"real-recovery",ignore_errors=True)

def _recover_short(topic,language,target):
    from local_voice import synthesize,provenance
    from long_video import real_word_captions
    from purffle_shorts.timing import Word
    from short_caption_style import recovery_captions
    from long_still_recovery import stills
    from media_validation import QualityValidator,SceneMatcher,SceneSpec
    from portrait_layout import center_filter
    from video_sources import LicenseValidator
    from era_policy import scene_era, footage_allowed
    from geography_policy import scene_requirement,require_geography
    from output_qa import validate_timeline
    target=Path(target).resolve()
    if not (target/"reviewed-script.json").is_file():
        recover_approved_dossier(topic,language,target)
    data=json.loads((target/"reviewed-script.json").read_text(encoding="utf8"))
    if (data.get("reviewed") is not True or data.get("topic")!=topic
            or data.get("language")!=language or not 2<=len(data.get("scenes",[]))<=6):
        raise RuntimeError("No matching source-reviewed narration available")
    try:
        previous=json.loads((target/"footage-report.json").read_text(encoding="utf8"))
    except (OSError,ValueError):
        previous={}
    matcher=SceneMatcher(threshold=.23)
    quality=QualityValidator()
    work=target/"real-recovery"
    work.mkdir(exist_ok=True)
    seen=set(); clips=[]; credits=[]; caption_words=[]; offset=0.
    from studio_runtime import StrictVisuals
    from production_checkpoint import digest
    # Use the existing source list only. Isolated duplicate ledger, report
    # and downloader; the new fallback never overwrites original diagnostics.
    env_keys=("FOOTAGE_USED_PATH","FOOTAGE_REPORT")
    old_env={key:os.environ.get(key) for key in env_keys}
    os.environ["FOOTAGE_USED_PATH"]=str(work/"used.json")
    os.environ["FOOTAGE_REPORT"]=str(target/"recovery-footage-report.json")
    try:
        from media_validation import VideoDownloader
        visuals=StrictVisuals(SimpleNamespace(offline=False,width=1080,height=1920,language=language,
            visual_sources=os.environ.get("VISUAL_SOURCES","pixabay,wikimedia-video,nasa-video,archive-video,nps-video,usgs-video,freenaturestock-video").split(",")),
            downloader=VideoDownloader(cache_dir=work/"downloads"),matcher=matcher)
    finally:
        # StrictVisuals captures the ledger path at construction. _save
        # reads the report path dynamically, so set it only during recovery.
        for key,value in old_env.items():
            if value is None: os.environ.pop(key,None)
            else: os.environ[key]=value
    base=["ffmpeg","-hide_banner","-nostdin","-y","-v","error","-filter_threads","1"]
    for i,scene in enumerate(data["scenes"],1):
        if not scene["visual_subject"] or not scene["visual_search_query"]:
            raise RuntimeError("Reviewed script has no concrete scene subject")
        speech=synthesize(scene["narration"],work/f"voice-{i}",SimpleNamespace(language=language))
        duration=float(speech.duration)
        real_word_captions(speech,offset)  # independently validate native word timing
        caption_words.extend(Word(w.text,offset+float(w.start),offset+float(w.end)) for w in speech.words)
        offset+=duration
        clip=work/f"scene-{i}.mp4"
        chosen=None
        for row in previous.get("scenes",[]):
            if row.get("index")!=i or row.get("status")!="selected":
                continue
            source_metadata=row.get("metadata_text","")
            if not source_metadata or not footage_allowed(row.get("source",""),scene_era(scene),
                                   source_metadata,row.get("recorded_date","")):
                continue
            try:
                # Actual source proof, never the search query itself.
                geo=row.get("geography_evidence",{})
                required=scene_requirement(scene,topic)
                if required and (not geo.get("accepted") or not set(required)<=set(geo.get("provider_claims",[]))):
                    continue
            except (TypeError,ValueError):
                continue
            lic=row.get("license",{})
            candidate=Path(row.get("downloaded_file") or "")
            if not candidate.is_file() or not LicenseValidator.validate(lic) or lic.get("attribution_required"):
                continue
            if not row.get("sha256") or digest(candidate)!=row["sha256"]:
                continue
            if row.get("plan",{}).get("object","").casefold()!=scene["visual_subject"].casefold():
                continue
            if row.get("match",{}).get("portrait_integrity",{}).get("verified") is not True:
                continue
            try:
                quality.validate(candidate,need=duration)
                spec=SceneSpec(main_character="",object=scene["visual_subject"],
                    action="ambient",visual_search_query=scene["visual_search_query"])
                from video_first_policy import check_topic_metadata
                from opening_impact import _first_frames
                from crop_subject_policy import verify_crop_subject
                from visual_director import build_contract,metadata_allows,verify_visible_event_or_illustrative_subject
                check_topic_metadata(topic,source_metadata+" "+str(lic.get("source_page","")))
                contract=build_contract(SimpleNamespace(**scene),topic,i)
                if not metadata_allows(contract,source_metadata+" "+str(lic.get("source_page",""))):
                    continue
                match=matcher.match(candidate,spec,metadata=source_metadata,duration=duration)
                frames=_first_frames(candidate,focus=.5,seconds=(.15,duration*.45,max(.2,duration*.85)))
                verify_crop_subject(frames,spec,matcher)
                verify_visible_event_or_illustrative_subject(candidate,duration,.5,contract,match,scorer=matcher._similarities,opening=i==1)
                chosen=candidate
                visuals.used_hashes.add(row["sha256"])
                visuals.used.add(str(row["source"])+":"+str(row["id"]))
                credits.append({"source":row["source"],"id":row["id"],"license":lic,
                                "geography_evidence":row.get("geography_evidence",{}),"media_type":"video","scene":i})
                break
            except Exception:
                continue
        if chosen is None:
            old_report=os.environ.get("FOOTAGE_REPORT")
            os.environ["FOOTAGE_REPORT"]=str(target/"recovery-footage-report.json")
            try:
                chosen,row=search_recovery_clip(visuals,scene,topic,i,duration+.05,work)
                credits.append({"source":row["source"],"id":row["id"],"license":row["license"],
                                "geography_evidence":row.get("geography_evidence",{}),"media_type":"video","scene":i})
            except Exception as exc:
                print(f"[RECOVERY STOCK UNAVAILABLE] scene={i} {type(exc).__name__}",flush=True)
            finally:
                if old_report is None: os.environ.pop("FOOTAGE_REPORT",None)
                else: os.environ["FOOTAGE_REPORT"]=old_report
        if chosen:
            credits[-1]["screen_seconds"]=duration
            inputs=["-i",str(chosen)]
            vf=center_filter(1080,1920)+",fps=30,format=yuv420p"
        else:
            # Try two shorter, independently verified moving clips before
            # using a still. Preserve all narration and actual audio timing.
            pieces=[]
            piece_frames=round(duration*30)
            lengths=[piece_frames//2,piece_frames-piece_frames//2] if duration>=4 else [piece_frames]
            if len(lengths)==2:
                os.environ["FOOTAGE_REPORT"]=str(target/"recovery-footage-report.json")
                try:
                    for j,n in enumerate(lengths):
                        try:
                            path,row=search_recovery_clip(visuals,scene,topic,i,n/30+.05,work)
                            pieces.append((path,{"source":row["source"],"id":row["id"],"license":row["license"],
                                "geography_evidence":row.get("geography_evidence",{}),"media_type":"video","scene":i},n))
                        except Exception as exc:
                            print("[SHORT VIDEO SEGMENT UNAVAILABLE]",i,j,type(exc).__name__,flush=True)
                            pieces.append((None,None,n))
                finally:
                    if old_report is None: os.environ.pop("FOOTAGE_REPORT",None)
                    else: os.environ["FOOTAGE_REPORT"]=old_report
            else:
                pieces=[(None,None,piece_frames)]
            # If neither short clip works, one still is sufficient for this
            # last-resort scene. Do not require two photos unnecessarily.
            if all(p is None for p,c,n in pieces):
                pieces=[(None,None,piece_frames)]
            manifests=[]
            for j,(path,credit,n) in enumerate(pieces):
                part=work/f"scene-{i}-piece-{j}.mp4"
                if path is None:
                    photos=stills({**scene,"topic":topic},i*10+j,work,seen,size=(1080,1920),limit=1,require_verified=True,matcher=matcher)
                    path,credit=photos[0]
                    input_args=["-loop","1","-framerate","30","-i",str(path)]
                    filter_text="setsar=1,format=yuv420p"
                else:
                    input_args=["-i",str(path)]
                    filter_text=center_filter(1080,1920)+",fps=30,format=yuv420p"
                run(base+input_args+["-vf",filter_text,"-frames:v",str(n),"-an","-r","30",
                    "-c:v","libx264","-preset","veryfast","-crf","22","-threads","2",str(part)])
                credits.append({**credit,"scene":i,"screen_seconds":n/30})
                manifests.append(part)
            joined=work/f"scene-{i}-pieces.txt"
            joined.write_text("".join("file '"+str(p)+"'\n" for p in manifests),encoding="utf8")
            inputs=["-f","concat","-safe","0","-i",str(joined)]
            vf="setsar=1,format=yuv420p"
        run(base+inputs+["-i",str(speech.audio),"-t",f"{duration:.3f}","-map","0:v:0",
             "-map","1:a:0","-vf",vf,"-r","30","-c:v","libx264","-preset","veryfast",
             "-crf","22","-threads","2","-c:a","aac","-b:a","160k","-ar","44100","-ac","2",str(clip)])
        clips.append(clip)
    captions=target/"captions.srt"
    playlist,band_y,subtitle_text=recovery_captions(caption_words,offset,language,work)
    captions.write_text(subtitle_text,encoding="utf8")
    manifest=work/"concat.txt"
    manifest.write_text("".join("file '"+str(p)+"'\n" for p in clips),encoding="utf8")
    out=target/"review-video.mp4"
    run(base+["-f","concat","-safe","0","-i",str(manifest),
             "-f","concat","-safe","0","-i",str(playlist.resolve()),
             "-filter_complex",f"[0:v][1:v]overlay=x=0:y={band_y}:eof_action=pass:repeatlast=0[v]",
             "-map","[v]","-map","0:a:0","-t",f"{offset:.3f}","-r","30",
             "-c:v","libx264","-preset","veryfast","-crf","22","-threads","2","-c:a","copy",
             "-movflags","+faststart",str(out)])
    try:
        qa=validate_timeline(out,captions,expected_size=(1080,1920),expected_duration=offset,
                             expected_text=" ".join(scene["narration"] for scene in data["scenes"]))
    except Exception:
        out.unlink(missing_ok=True)
        raise
    from video_first_policy import media_mix
    mix=media_mix(credits)
    (target/"media-mix.json").write_text(json.dumps(mix,indent=2),encoding="utf8")
    print("[VIDEO FIRST]",mix,flush=True)
    (target/"credits.json").write_text(json.dumps(credits,indent=2,ensure_ascii=False),encoding="utf8")
    (target/"output-qa.json").write_text(json.dumps(qa,indent=2),encoding="utf8")
    shutil.rmtree(work,ignore_errors=True)
    return {"status":"review","mp4":str(out),"resolution":"1080x1920","duration":qa["duration"],
            "quality_mode":"verified_mixed_media_review" if mix["target_met"] else "photo_heavy_or_low_video_share_review",
            "media_mix":mix,"narrator_mode":"piper:"+provenance(language)["model"],
            "photo_uses":sum(c.get("media_type")=="photo" for c in credits),
            "video_uses":sum(c.get("media_type")=="video" for c in credits),
            "error":"Mixed-media fallback; review before publication"}
