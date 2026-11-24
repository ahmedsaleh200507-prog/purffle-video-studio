"""Recover a source-reviewed Shorts script with verified real footage/photos and locked Piper."""
import json
import os
import subprocess
import shutil
from pathlib import Path
from types import SimpleNamespace

def save_reviewed_script(screenplay,language,topic):
    dest=os.environ.get("PURFFLE_REVIEWED_SCRIPT")
    if not dest:
        return
    scenes=[]
    for scene in screenplay.scenes:
        scenes.append({"narration":str(scene.narration),
                       "visual_subject":str(getattr(scene,"object","") or ""),
                       "time":str(getattr(scene,"time","") or ""),
                       "visual_search_query":str(getattr(scene,"visual_search_query","") or "")})
    Path(dest).write_text(json.dumps({"topic":topic,"language":language,
                    "scenes":scenes,"reviewed":True},ensure_ascii=False),encoding="utf8")

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
    from long_video import real_word_captions,srt_time
    from long_still_recovery import stills
    from media_validation import QualityValidator,SceneMatcher,SceneSpec
    from portrait_layout import center_filter
    from video_sources import LicenseValidator
    from era_policy import scene_era, footage_allowed
    from geography_policy import scene_requirement,require_geography
    from output_qa import validate_timeline
    target=Path(target).resolve()
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
    seen=set(); clips=[]; credits=[]; cues=[]; offset=0.
    base=["ffmpeg","-hide_banner","-nostdin","-y","-v","error","-filter_threads","1"]
    for i,scene in enumerate(data["scenes"],1):
        if not scene["visual_subject"] or not scene["visual_search_query"]:
            raise RuntimeError("Reviewed script has no concrete scene subject")
        speech=synthesize(scene["narration"],work/f"voice-{i}",SimpleNamespace(language=language))
        duration=float(speech.duration)
        cues.extend(real_word_captions(speech,offset))
        offset+=duration
        clip=work/f"scene-{i}.mp4"
        chosen=None
        for row in previous.get("scenes",[]):
            if row.get("index")!=i or row.get("status")!="selected":
                continue
            if not footage_allowed(row.get("source",""),scene_era(scene),
                                   row.get("plan",{}).get("visual_search_query",""),row.get("recorded_date","")):
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
            if row.get("plan",{}).get("object","").casefold()!=scene["visual_subject"].casefold():
                continue
            if row.get("match",{}).get("portrait_integrity",{}).get("verified") is not True:
                continue
            try:
                quality.validate(candidate,need=duration)
                spec=SceneSpec(main_character="",object=scene["visual_subject"],
                    action="ambient",visual_search_query=scene["visual_search_query"])
                matcher.match(candidate,spec,metadata=row.get("plan",{}).get("visual_search_query",""),duration=duration)
                chosen=candidate
                credits.append({"source":row["source"],"id":row["id"],"license":lic,"media_type":"video","scene":i})
                break
            except Exception:
                continue
        if chosen:
            inputs=["-i",str(chosen)]
            vf=center_filter(1080,1920)+",fps=30,format=yuv420p"
        else:
            photos=stills({**scene,"topic":topic},i,work,seen,size=(1080,1920),limit=1,require_verified=True,matcher=matcher)
            path,credit=photos[0]
            credits.append({**credit,"scene":i})
            inputs=["-loop","1","-framerate","30","-i",str(path)]
            vf="setsar=1,format=yuv420p"
        run(base+inputs+["-i",str(speech.audio),"-t",f"{duration:.3f}","-map","0:v:0",
             "-map","1:a:0","-vf",vf,"-r","30","-c:v","libx264","-preset","veryfast",
             "-crf","22","-threads","2","-c:a","aac","-b:a","160k","-ar","44100","-ac","2",str(clip)])
        clips.append(clip)
    captions=target/"captions.srt"
    captions.write_text("".join(f"{i}\n{srt_time(a)} --> {srt_time(b)}\n{line}\n\n"
                    for i,(a,b,line) in enumerate(cues,1)),encoding="utf8")
    manifest=work/"concat.txt"
    manifest.write_text("".join("file '"+str(p)+"'\n" for p in clips),encoding="utf8")
    out=target/"review-video.mp4"
    sub=str(captions).replace("\\","\\\\").replace(":","\\:").replace("'","\\'")
    run(base+["-f","concat","-safe","0","-i",str(manifest),"-vf",
             "subtitles='"+sub+"':force_style='FontSize=17,Alignment=2,MarginV=42'",
             "-c:v","libx264","-preset","veryfast","-crf","22","-threads","2","-c:a","copy",
             "-movflags","+faststart",str(out)])
    try:
        qa=validate_timeline(out,captions,expected_size=(1080,1920),expected_duration=offset)
    except Exception:
        out.unlink(missing_ok=True)
        raise
    (target/"credits.json").write_text(json.dumps(credits,indent=2,ensure_ascii=False),encoding="utf8")
    (target/"output-qa.json").write_text(json.dumps(qa,indent=2),encoding="utf8")
    shutil.rmtree(work,ignore_errors=True)
    return {"status":"review","mp4":str(out),"resolution":"1080x1920","duration":qa["duration"],
            "quality_mode":"verified_mixed_media_review","narrator_mode":"piper:"+provenance(language)["model"],
            "photo_uses":sum(c.get("media_type")=="photo" for c in credits),
            "video_uses":sum(c.get("media_type")=="video" for c in credits),
            "error":"Mixed-media fallback; review before publication"}
