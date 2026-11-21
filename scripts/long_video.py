"""Experimental long-form documentary renderer. Shorts workflow remains untouched."""
import argparse, json, os, re, subprocess
from pathlib import Path
from types import SimpleNamespace

OUT = Path("long_video_output")
QUERIES = ["volcano eruption", "lava flow", "volcano smoke", "volcano aerial",
           "volcanic ash", "volcano crater", "molten lava", "volcanic mountain"]


def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf8")


def run(args, timeout=1800):
    p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if p.returncode:
        raise RuntimeError(f"{Path(args[0]).name}: exit {p.returncode}, {p.stderr[-250:]}")
    return p.stdout


def probe(path):
    d = json.loads(run(["ffprobe","-v","error","-show_streams","-show_format",
                        "-of","json",str(path)],60))
    v = next((x for x in d["streams"] if x["codec_type"]=="video"),{})
    a = next((x for x in d["streams"] if x["codec_type"]=="audio"),{})
    return float(d["format"].get("duration",0)), int(v.get("width",0)), int(v.get("height",0)), bool(a)


def words(s):
    return len(re.findall(r"\b[\w'-]+\b",s))


def chapters(topic):
    from long_script import build_documentary
    return build_documentary(topic)

def voice_segments(text):
    """Preserve narration exactly, while keeping 2-6 natural speech segments.

    Merge the shortest adjacent sentences as needed instead of cutting every
    25 words mid-sentence. The approved voice code validates the entire spoken
    transcript and independently validates each real audio segment.
    """
    pieces = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]
    while len(pieces) > 6:
        index = min(range(len(pieces)-1),
                    key=lambda k: len(pieces[k]) + len(pieces[k+1]))
        pieces[index:index+2] = [pieces[index] + " " + pieces[index+1]]
    if (not 2 <= len(pieces) <= 6 or
            any(not 10 <= len(piece) <= 350 or words(piece) < 6 for piece in pieces)):
        raise RuntimeError("Narration cannot be segmented safely at sentence boundaries")
    if " ".join(pieces) != " ".join(text.split()):
        raise RuntimeError("Sentence chunking changed the narration")
    return pieces


def narrate(data,work):
    from english_reference_policy import enforce_english_reference_only
    from approved_reference_voice import synthesize
    enforce_english_reference_only("en")
    audios, lines, offset=[],[],0.0
    for i,c in enumerate(data):
        text=c["narration"]
        # Real sentence boundaries help the approved TTS worker avoid clipped
        # speech; the old fixed 25-word slices cut clauses in mid-sentence.
        segments = voice_segments(text)
        speech=synthesize(text,work/f"voice-{i+1}",SimpleNamespace(language="en"),
                          segments=segments, long_form=True)
        if not Path(speech.audio).is_file() or not speech.words or not 20<=speech.duration<=95:
            raise RuntimeError(f"Chapter {i+1} approved voice invalid")
        audios.append((Path(speech.audio),float(speech.duration)))
        for j in range(0,len(speech.words),6):
            g=speech.words[j:j+6]
            lines.append((offset+g[0].start,offset+g[-1].end," ".join(x.word.strip() for x in g)))
        offset+=speech.duration
        print(f"[VOICE] chapter {i+1}/14, seconds={speech.duration:.1f}",flush=True)
    if not 540<=offset<=660:
        raise RuntimeError(f"Real narration duration={offset:.1f}s outside 9-11 min; no padding")
    return audios,lines,offset


def srt_time(t):
    ms=round(t*1000)
    h,ms=divmod(ms,3600000)
    m,ms=divmod(ms,60000)
    s,ms=divmod(ms,1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def find_stock(index,seconds,seen,work):
    from video_sources import ProviderRegistry
    from media_validation import VideoDownloader,QualityValidator
    reg=ProviderRegistry()
    dl=VideoDownloader(cache_dir=work/"downloads",max_bytes=140*1024*1024)
    val=QualityValidator(min_short_side=720)
    chosen=[]
    for k in range(5):
        query=QUERIES[(index*3+k)%len(QUERIES)]
        for provider in ("pexels","pixabay"):
            for candidate in reg.search(provider,query)[:30]:
                key=(candidate.source,str(candidate.id))
                if key in seen: continue
                if not any(x in candidate.text.lower() for x in ("volcan","lava","magma","eruption","crater","ash")):
                    continue
                try:
                    path=dl.download(candidate.url)
                    q=val.validate(path)
                    duration=float(q["duration"])
                    if int(q["width"])<1280 or int(q["height"])<720 or duration<seconds/1.5:
                        continue
                    seen.add(key)
                    lic=candidate.extra["license"]
                    chosen.append((path,duration,
                                   {"source":candidate.source,"id":candidate.id,
                                    "creator":lic["creator"],"license":lic["id"],
                                    "source_page":lic["source_page"],"query":query}))
                    if len(chosen)>=4:return chosen
                except Exception as ex:
                    print("[STOCK REJECT]",type(ex).__name__,flush=True)
    raise RuntimeError(f"Chapter {index+1}: only {len(chosen)}/4 verified unique real clips")


def render_scene(i,audio,duration,stock,work):
    shotdir=work/f"shots-{i:02d}"
    shotdir.mkdir(parents=True,exist_ok=True)
    files=[]
    wanted=duration/len(stock)
    for j,(path,srcdur,credit) in enumerate(stock):
        factor=max(1.0,wanted/srcdur)
        if factor>1.5:raise RuntimeError("Insufficient real motion for scene")
        dest=shotdir/f"shot-{j:02d}.mp4"
        vf=(f"setpts={factor:.6f}*(PTS-STARTPTS),"
            "scale=1920:1080:force_original_aspect_ratio=increase,"
            "crop=1920:1080,fps=30,format=yuv420p")
        run(["ffmpeg","-hide_banner","-nostdin","-y","-loglevel","error",
             "-i",str(path),"-t",f"{wanted:.3f}","-an","-vf",vf,
             "-c:v","libx264","-preset","veryfast","-crf","25",str(dest)],900)
        files.append(dest)
    manifest=shotdir/"concat.txt"
    manifest.write_text("\n".join("file '"+str(x.resolve())+"'" for x in files)+"\n")
    output=work/f"chapter-{i:02d}.mp4"
    run(["ffmpeg","-hide_banner","-nostdin","-y","-loglevel","error",
         "-f","concat","-safe","0","-i",str(manifest),"-i",str(audio),
         "-t",f"{duration:.3f}","-map","0:v:0","-map","1:a:0",
         "-c:v","copy","-c:a","aac","-b:a","160k",str(output)],900)
    return output


def finish(scene_paths,subtitles,target,work):
    manifest=work/"all-scenes.txt"
    manifest.write_text("\n".join("file '"+str(x.resolve())+"'" for x in scene_paths)+"\n")
    stitched=work/"stitched.mp4"
    run(["ffmpeg","-hide_banner","-nostdin","-y","-loglevel","error",
         "-f","concat","-safe","0","-i",str(manifest),"-c","copy",str(stitched)],1500)
    run(["ffmpeg","-hide_banner","-nostdin","-y","-loglevel","error",
         "-i",str(stitched),"-i",str(subtitles),"-map","0:v:0","-map","0:a:0",
         "-map","1:s:0","-c:v","copy","-c:a","copy","-c:s","mov_text",
         "-movflags","+faststart",str(target)],1500)


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--topic",default="Why do volcanoes erupt?")
    p.add_argument("--language",choices=("en",),default="en")
    p.add_argument("--self-test",action="store_true")
    a=p.parse_args()
    if a.self_test:
        assert srt_time(60.53)=="00:01:00,530"
        assert words("Volcanoes can erupt suddenly.")==4
        print("Static long-video tests passed")
        return
    if "volcan" not in a.topic.casefold() and "lava" not in a.topic.casefold():
        raise RuntimeError("The first long-video pilot supports only volcano/lava subjects")
    output,work=OUT/"result",OUT/"work"
    output.mkdir(parents=True,exist_ok=True)
    work.mkdir(parents=True,exist_ok=True)
    report={"mode":"long_video","status":"failed","mp4":None,"topic":a.topic,
            "target_duration":600,"resolution":"1920x1080"}
    stage="preflight"
    try:
        from english_reference_policy import enforce_english_reference_only
        enforce_english_reference_only("en")
        stage="script"
        text=chapters(a.topic)
        save(output/"script.json",{"chapters":text})
        stage="reference_voice"
        audio,subs,voice_seconds=narrate(text,work)
        with (output/"captions.srt").open("w",encoding="utf8") as f:
            for j,(start,end,line) in enumerate(subs,1):
                f.write(f"{j}\n{srt_time(start)} --> {srt_time(end)}\n{line}\n\n")
        stage="real_stock"
        used,scenes,credits=set(),[],[]
        for i,(wav,seconds) in enumerate(audio):
            clips=find_stock(i,seconds/4,used,work)
            credits += [c[2] for c in clips]
            stage=f"render_chapter_{i+1}"
            scenes.append(render_scene(i+1,wav,seconds,clips,work))
            print(f"[RENDER] {i+1}/14",flush=True)
            stage="real_stock"
        stage="final_mp4"
        final=output/"long-video.mp4"
        finish(scenes,output/"captions.srt",final,work)
        duration,width,height,audible=probe(final)
        if not (540<=duration<=660 and width==1920 and height==1080 and audible):
            raise RuntimeError("Final video failed measured duration/1080p/audio validation")
        save(output/"credits.json",credits)
        report.update(status="ok",mp4="long-video.mp4",duration=duration,
                      clips=len(credits),narration_duration=voice_seconds,
                      note="Trial: stock metadata matched but independent shot-level semantic CLIP QA not available")
    except Exception as e:
        report.update(stage=stage,error=(type(e).__name__+": "+str(e))[:800])
        raise
    finally:
        save(output/"report.json",report)


if __name__=="__main__":
    main()
