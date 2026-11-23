"""Free offline production path: create ACTUAL complete MP4s without LLM or stock.

Used ONLY after normal Shorts or long documentary production fails. 2D
educational animation with locally generated graphics, text, subtitles and
offline voice. No Gemini, Groq, external photos, paid API or web access.
Quality mode is reported honestly as offline_2d_fallback, never claimed as
verified real-stock footage or as a 'preview'. Publishes a complete playable
H.264/AAC film if FFmpeg is operational.

For topics outside the locally fact-checked pack, visuals discuss the topic
as questions rather than inventing scientific explanations. That fallback
is less informative, but it still makes a proper complete film.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import textwrap
from PIL import Image, ImageDraw, ImageFont

SHORT_SECONDS = 32
LONG_SECONDS = 602
FPS = 24

# Limited, common-knowledge fact packs for requested EN/DE education topics.
# Not a substitute for live science review and not represented as stock video.
FACTS = {
 "rocket": {
  "en": [
   "Reusable rockets reduce speed before returning toward the ground.",
   "Some boosters turn around using carefully timed engine burns.",
   "Guidance computers steer the rocket with fins and engine thrust.",
   "The landing legs support the booster as it touches down.",
   "Successful recovery allows engineers to inspect and reuse hardware.",
   "Landing a tall booster is a difficult problem in control engineering.",
   "Engines must adjust thrust to slow the vehicle at the right moment.",
  ]},
 "eclipse": {
  "de": [
   "Eine Sonnenfinsternis entsteht, wenn der Mond zwischen Sonne und Erde steht.",
   "Der Mond wirft dabei einen Schatten auf einen Teil der Erde.",
   "Im Kernschatten kann die Sonne kurz vollständig verdeckt sein.",
   "Außerhalb des Kernschattens sieht man eine partielle Sonnenfinsternis.",
   "Nicht bei jedem Neumond entsteht eine Finsternis: Die Mondbahn ist geneigt.",
   "Die Sonnenkorona ist bei einer totalen Finsternis besonders gut sichtbar.",
   "Ohne geeignete Schutzbrille darf man nicht direkt in die Sonne schauen.",
  ]},
 "meteor": {
  "en": [
   "A meteor is the light produced when a space rock enters our atmosphere.",
   "Air in front of the fast-moving rock becomes extremely hot.",
   "The glowing trail can be brighter than the object itself.",
   "Small meteoroids often break apart before reaching the ground.",
   "A fragment that survives and reaches the surface is called a meteorite.",
   "Meteor showers happen when Earth crosses streams of space debris.",
   "The streaks can appear very quickly across the night sky.",
  ]},
 "tornado": {
  "de": [
   "Tornados können sich aus starken Gewittern entwickeln.",
   "Unterschiedliche Windgeschwindigkeiten und Richtungen fördern Luftrotation.",
   "Starke Aufwinde können die rotierende Luft aufrichten und verstärken.",
   "Ein Tornado ist eine rotierende Luftsäule mit Bodenkontakt.",
   "Die sichtbare Trichterwolke besteht aus kondensierten Wassertröpfchen.",
   "Nicht alle Tornados sind als durchgehender Trichter zu erkennen.",
   "Bei Tornadowarnung bieten innenliegende Räume im Untergeschoss Schutz.",
  ]},
 "lava": {
  "en": [
   "Lava glows because it is hot enough to emit visible light.",
   "Very hot molten rock can appear bright yellow or orange.",
   "As lava cools, its glow often becomes deeper red.",
   "The outside can darken while hotter material still moves underneath.",
   "Lava comes from magma that has reached Earth's surface.",
   "Its color depends on temperature, not simply on the rock's name.",
   "Even a dark-looking lava crust can hide dangerous heat below.",
  ]},
 "electric": {
  "en": [
   "An electric car stores energy in a rechargeable battery pack.",
   "Power electronics control how electricity reaches the drive motor.",
   "The motor converts electrical energy into motion at the wheels.",
   "Regenerative braking can recover some energy when a car slows down.",
   "Charging transfers electricity from a supply into the battery.",
   "The battery management system monitors temperature and charge.",
   "Electric vehicles do not produce tailpipe exhaust while driving.",
  ]},
 "aurora": {
  "de": [
   "Polarlichter entstehen durch Teilchen aus dem Weltraum.",
   "Das Erdmagnetfeld lenkt geladene Teilchen in Richtung der Polarregionen.",
   "In der oberen Atmosphäre stoßen die Teilchen mit Gasen zusammen.",
   "Angeregte Sauerstoffatome können grünes oder rotes Licht aussenden.",
   "Stickstoff kann zu bläulichen und violetten Farben beitragen.",
   "Die Lichtvorhänge verändern ihre Form durch Bewegungen der Teilchen.",
   "Starke Sonnenaktivität kann Polarlichter auch weiter südlich sichtbar machen.",
  ]},
 "elnino": {
  "en": [
   "El Niño is linked to unusually warm surface water in the central and eastern tropical Pacific.",
   "Trade winds over the tropical Pacific can weaken during El Niño.",
   "Changes in ocean temperature alter patterns of rainfall and rising air.",
   "The effects can influence weather far beyond the Pacific Ocean.",
   "Some regions become wetter while others may become drier.",
   "El Niño is one phase of the El Niño Southern Oscillation.",
   "Scientists monitor ocean temperatures and atmospheric pressure to track it.",
  ]},
 "chip": {
  "de": [
   "Computerchips bestehen aus vielen winzigen elektronischen Bauelementen.",
   "Transistoren wirken in digitalen Schaltungen wie steuerbare Schalter.",
   "Schaltkreise verarbeiten Informationen in Form elektrischer Signale.",
   "Moderne Prozessoren enthalten sehr viele Transistoren auf kleiner Fläche.",
   "Ein Takt synchronisiert zahlreiche Arbeitsschritte im Prozessor.",
   "Speicher und Prozessor arbeiten zusammen, um Programme auszuführen.",
   "Die Wärmeentwicklung macht eine geeignete Kühlung notwendig.",
  ]},
 "telescope": {
  "en": [
   "Space telescopes observe the universe from above Earth's atmosphere.",
   "Hubble is known for observing distant galaxies and stellar nurseries.",
   "The James Webb Space Telescope is designed mainly for infrared observations.",
   "Infrared light can reveal objects hidden by some clouds of cosmic dust.",
   "A telescope collects faint light with large mirrors and precise instruments.",
   "Scientists analyze different wavelengths to study stars and planets.",
   "The light from distant galaxies has traveled through space for billions of years.",
  ]},
 "octopus": {"en": [
   "Octopuses have three hearts that move blood around the body.",
   "Two hearts send blood through the gills to take up oxygen.",
   "A third heart pumps oxygen-rich blood to the rest of the body.",
   "Octopuses use gills to breathe underwater.",
  ]},
 "ship": {"en": [
   "A steel ship can float because its hull displaces water.",
   "The upward buoyant force depends on the water displaced.",
   "A large hollow hull makes the vessel's average density low enough to float.",
   "Cargo changes how deeply a ship sits in the water.",
  ]},
}

def _kind(topic: str):
    s = topic.casefold()
    tests = [
        ("eclipse", ("sonnenfinsternis", "solar eclipse")),
        ("aurora", ("polarlichter", "northern lights", "aurora")),
        ("elnino", ("el niño", "el nino")),
        ("chip", ("computerchips", "microchip", "processor", "computer chip")),
        ("telescope", ("telescope", "teleskop")),
        ("rocket", ("rocket", "rakete")),
        ("meteor", ("meteor",)),
        ("tornado", ("tornado", "tornados")),
        ("lava", ("lava",)),
        ("electric", ("electric car", "elektroauto", "elektrofahrzeug")),
        ("octopus", ("octopus", "octopi", "oktopus")),
        ("ship", ("ship", "schiff")),
    ]
    return next((k for k, terms in tests if any(t in s for t in terms)), "general")


def _text_scenes(topic, language, mode):
    kind = _kind(topic)
    available = FACTS.get(kind, {})
    facts = available.get(language) or available.get("en") or []
    count = 4 if mode == "short" else 14
    if not facts:
        if language == "de":
            facts = [
              "Dieses Video beschäftigt sich mit der Frage: " + topic.rstrip("?") + ".",
              "Wir betrachten die wichtigsten Begriffe und sichtbaren Merkmale.",
              "Danach ordnen wir ein, welche Mechanismen eine Rolle spielen können.",
              "Zum Schluss fassen wir die offene Frage und die zentralen Punkte zusammen."
            ]
        else:
            facts = [
              "This video explores the question: " + topic.rstrip("?") + ".",
              "We begin by identifying the main subject and what people can observe.",
              "Next, we examine the different parts of the question.",
              "Finally, we bring the main ideas together and consider what remains to be explained."
            ]
    chosen = [facts[i % len(facts)] for i in range(count)]
    return kind, chosen, bool(available.get(language))


def _font(px):
    for location in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ):
        try:
            return ImageFont.truetype(location, px)
        except OSError:
            pass
    return ImageFont.load_default()


def _illustration(draw, kind, w, h, shift=0):
    cx, cy = int(w*.71), int(h*.34)
    scale = min(w/1920, h/1080)
    def e(box, fill, outline=None, width=3):
        draw.ellipse(tuple(int(x) for x in box), fill=fill, outline=outline, width=width)
    if kind == "rocket":
        draw.polygon([(cx,cy-185*scale),(cx-66*scale,cy+75*scale),(cx+66*scale,cy+75*scale)],fill=(222,231,243))
        e((cx-48*scale,cy-68*scale,cx+48*scale,cy+28*scale),(69,159,207))
        draw.polygon([(cx-50*scale,cy+65*scale),(cx-120*scale,cy+140*scale),(cx+120*scale,cy+140*scale),(cx+50*scale,cy+65*scale)],fill=(190,109,66))
        draw.polygon([(cx-34*scale,cy+145*scale),(cx,cy+255*scale),(cx+34*scale,cy+145*scale)],fill=(250,153,48))
    elif kind in ("eclipse","aurora","elnino","telescope","meteor"):
        e((cx-180*scale,cy-180*scale,cx+180*scale,cy+180*scale),(39,101,151))
        if kind=="eclipse":
            e((cx-168*scale,cy-168*scale,cx+168*scale,cy+168*scale),(244,174,57))
            e((cx-119*scale,cy-119*scale,cx+169*scale,cy+169*scale),(22,29,49))
        elif kind=="aurora":
            for i in range(6):
                xx=cx-int(175*scale)+i*int(53*scale)
                draw.polygon([(xx,cy-185*scale),(xx+20*scale,cy+170*scale),(xx+80*scale,cy-185*scale)],fill=(54,135+i*12,100+i*14))
        elif kind=="meteor":
            draw.line((cx-250*scale,cy-190*scale,cx+140*scale,cy+120*scale), fill=(247,197,77),width=max(4,int(22*scale)))
            e((cx+105*scale,cy+88*scale,cx+171*scale,cy+154*scale),(255,210,94))
        elif kind=="telescope":
            draw.rectangle((cx-160*scale,cy-25*scale,cx+150*scale,cy+28*scale),fill=(202,212,230))
        else:
            for i in range(6):
                e((cx-(140-i*12)*scale,cy-(140-i*12)*scale,cx+(140-i*12)*scale,cy+(140-i*12)*scale),None,outline=(87+i*12,145+i*8,180+i*5))
    elif kind=="tornado":
        for i in range(18):
            y=cy-int(185*scale)+i*int(23*scale)
            span=max(14,int((170-i*8)*scale))
            draw.arc((cx-span,y-16*scale,cx+span,y+32*scale),0,290,fill=(171,193,211),width=max(2,int(8*scale)))
    elif kind=="lava":
        e((cx-180*scale,cy-100*scale,cx+180*scale,cy+240*scale),(114,52,42))
        draw.polygon([(cx-160*scale,cy+95*scale),(cx,cy-95*scale),(cx+150*scale,cy+125*scale),(cx+100*scale,cy+235*scale),(cx-95*scale,cy+235*scale)],fill=(240,116,37))
    elif kind in ("chip","electric"):
        draw.rounded_rectangle((cx-180*scale,cy-120*scale,cx+180*scale,cy+155*scale),radius=int(30*scale),fill=(72,154,191),outline=(175,237,255),width=max(3,int(8*scale)))
        if kind=="chip":
            for i in range(5):
                x=cx-int(100*scale)+i*int(50*scale)
                draw.line((x,cy-170*scale,x,cy+190*scale),fill=(94,204,176),width=max(2,int(6*scale)))
        else:
            e((cx-145*scale,cy+100*scale,cx-75*scale,cy+175*scale),(17,28,42))
            e((cx+75*scale,cy+100*scale,cx+145*scale,cy+175*scale),(17,28,42))
    elif kind=="octopus":
        e((cx-100*scale,cy-150*scale,cx+110*scale,cy+50*scale),(154,111,197))
        for i in range(8):
            angle=i*math.tau/8
            x=cx+math.cos(angle)*140*scale
            y=cy+math.sin(angle)*150*scale
            draw.line((cx,cy+60*scale,x,y+170*scale),fill=(159,112,200),width=max(5,int(16*scale)))
    elif kind=="ship":
        draw.polygon([(cx-220*scale,cy+75*scale),(cx+220*scale,cy+75*scale),(cx+155*scale,cy+170*scale),(cx-155*scale,cy+170*scale)],fill=(157,191,216))
        draw.rectangle((cx-100*scale,cy-40*scale,cx+110*scale,cy+73*scale),fill=(204,156,84))
    else:
        for i in range(6):
            rad=(90+i*37)*scale
            e((cx-rad,cy-rad,cx+rad,cy+rad),None,outline=(61+i*13,122+i*13,163+i*8),width=max(2,int(4*scale)))


def _poster(path, topic, statement, kind, index, count, language, size):
    w, h=size
    im=Image.new("RGB", size, (12,24,45))
    dr=ImageDraw.Draw(im)
    for y in range(h):
        r=14+int(10*y/h)
        g=28+int(24*y/h)
        b=49+int(32*y/h)
        dr.line((0,y,w,y),fill=(r,g,b))
    # Top title, chapter content and original geometric scene illustration.
    dr.rounded_rectangle((int(w*.055),int(h*.055),int(w*.49),int(h*.12)),
                         radius=max(4,int(w*.005)), fill=(32,86,105))
    sub="DOCUMENTARY • 2D" if language=="en" else "DOKUMENTATION • 2D"
    dr.text((int(w*.077),int(h*.072)),sub,font=_font(max(17,int(w*.012))),fill=(216,231,242))
    title_width=32 if w>h else 18
    name=textwrap.wrap(topic[:125],width=title_width,max_lines=3,placeholder="...")
    ty=int(h*.19)
    for line in name:
        dr.text((int(w*.067),ty),line,font=_font(max(24,int(w*.032))),fill=(249,249,255))
        ty+=int(w*.041)
    fact_width=42 if w>h else 23
    segments=textwrap.wrap(statement,width=fact_width,max_lines=7,placeholder="...")
    fy=max(int(h*.50),ty+int(h*.035))
    dr.rounded_rectangle((int(w*.048),fy-int(h*.035),int(w*.94),
                          min(h-int(h*.13),fy+len(segments)*int(w*.025)+int(h*.07))),
                         radius=int(w*.015),fill=(30,58,81))
    for i,line in enumerate(segments):
        dr.text((int(w*.073),fy+i*int(w*.027)),line,
                font=_font(max(21,int(w*.018))),fill=(230,239,245))
    _illustration(dr,kind,w,h)
    footer=f"{index+1:02d}/{count:02d}  •  OFFLINE 2D"
    dr.text((int(w*.066),int(h*.946)),footer,font=_font(max(16,int(w*.014))),fill=(170,198,209))
    im.save(path)


def _speak(text, language, work, index):
    wav=work/f"voice-{index:02d}.wav"
    espeak=shutil.which("espeak-ng") or shutil.which("espeak")
    if espeak:
        try:
            subprocess.run([espeak,"-v", "de" if language=="de" else "en-us",
                            "-s","145","-w",str(wav),text],
                           timeout=35,check=True,stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
            if wav.exists() and wav.stat().st_size>512:
                return wav,"espeak_offline_backup"
        except (OSError,subprocess.SubprocessError):
            pass
    textfile=work/f"speech-{index:02d}.txt"
    textfile.write_text(text,encoding="utf8")
    try:
        subprocess.run(["ffmpeg","-hide_banner","-nostdin","-loglevel","error","-y",
                        "-f","lavfi","-i",f"flite=textfile={textfile}:voice=kal",
                        "-ac","1",str(wav)],timeout=40,check=True,
                       stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        return wav,"flite_offline_backup"
    except (OSError,subprocess.SubprocessError):
        return None,"silent_audio_backup"


def _run(argv, timeout=180):
    subprocess.run(argv, check=True, timeout=timeout,
                   stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)


def _concat(chunks, out, work):
    manifest=work/"concat.txt"
    manifest.write_text("".join("file '"+str(x.resolve()).replace("'","'\\''")+"'\n"
                                for x in chunks),encoding="utf8")
    _run(["ffmpeg","-hide_banner","-nostdin","-loglevel","error","-y",
          "-f","concat","-safe","0","-i",str(manifest),"-c","copy",
          "-movflags","+faststart",str(out)],timeout=300)


def _probe(path):
    out=subprocess.check_output(
        ["ffprobe","-v","error","-show_format","-show_streams",
         "-of","json",str(path)],timeout=35)
    data=json.loads(out)
    return data


def make_video(*, topic, language, mode, output, root=None):
    """Actually render complete video and audio; no diagnostic-card shortcut."""
    if language not in ("en","de") or mode not in ("short","long"):
        raise ValueError("Only English/German short/long modes supported")
    path=Path(output)
    path.parent.mkdir(parents=True,exist_ok=True)
    w,h=(1080,1920) if mode=="short" else (1920,1080)
    total=SHORT_SECONDS if mode=="short" else LONG_SECONDS
    kind, facts, matched=_text_scenes(topic,language,mode)
    count=len(facts)
    seconds=total/count
    source_root=Path(root) if root else path.parent
    source_root.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="purffle-offline-",dir=source_root) as temp:
        work=Path(temp)
        chunks=[]
        captions=[]
        voices=[]
        for i,statement in enumerate(facts):
            poster=work/f"scene-{i:02d}.png"
            _poster(poster,topic,statement,kind,i,count,language,(w,h))
            wav,voice=_speak(statement,language,work,i)
            voices.append(voice)
            out=work/f"scene-{i:02d}.mp4"
            inputs=["-loop","1","-framerate",str(FPS),"-i",str(poster)]
            if wav is None:
                inputs+=["-f","lavfi","-i","anullsrc=channel_layout=stereo:sample_rate=44100"]
            else:
                inputs+=["-i",str(wav)]
            video_length=f"{seconds:.3f}"
            fade_out=max(0,seconds-.45)
            args=["ffmpeg","-hide_banner","-nostdin","-loglevel","error","-y",
                  *inputs,
                  "-t",video_length,"-map","0:v:0","-map","1:a:0",
                  "-vf",f"scale={w}:{h},fade=t=in:st=0:d=.3,fade=t=out:st={fade_out:.3f}:d=.3,format=yuv420p",
                  "-af","apad",
                  "-c:v","libx264","-preset","veryfast","-crf","25",
                  "-r",str(FPS),"-c:a","aac","-b:a","96k",
                  "-ar","44100","-ac","2",
                  "-movflags","+faststart",str(out)]
            _run(args,timeout=180 if mode=="short" else 480)
            chunks.append(out)
            start=i*seconds
            def srt_time(t):
                ms=int(round(t*1000))
                hours,ms=divmod(ms,3600000)
                minutes,ms=divmod(ms,60000)
                sec,ms=divmod(ms,1000)
                return f"{hours:02d}:{minutes:02d}:{sec:02d},{ms:03d}"
            captions.append(f"{i+1}\n{srt_time(start)} --> {srt_time(start+seconds-.1)}\n{statement}\n\n")
        _concat(chunks,path,work)
    data=_probe(path)
    stream=next(x for x in data["streams"] if x["codec_type"]=="video")
    audio=next((x for x in data["streams"] if x["codec_type"]=="audio"),None)
    duration=float(data["format"]["duration"])
    if (stream["width"],stream["height"])!=(w,h) or audio is None or abs(duration-total)>2.5:
        path.unlink(missing_ok=True)
        raise RuntimeError("offline_final_mp4_invalid")
    (path.parent/"captions.srt").write_text("".join(captions),encoding="utf8")
    (path.parent/"script.json").write_text(
        json.dumps({"topic":topic,"language":language,"mode":mode,
                    "scenes":[{"narration":x} for x in facts]},
                   ensure_ascii=False,indent=2),encoding="utf8")
    (path.parent/"credits.json").write_text(
        json.dumps({"mode":"locally_drawn_original_2d",
                    "not_real_stock":True,
                    "source_videos":[]},indent=2),encoding="utf8")
    return {"status":"ok","mp4":str(path),"duration":round(duration,2),
            "resolution":f"{w}x{h}","quality_mode":"offline_2d_fallback",
            "narrator_mode":",".join(sorted(set(voices))),
            "content_scope":("topic_fact_pack" if matched
                             else "generic_topic_outline_without_verified_claims"),
            "visual_mode":"original_2d_graphics_no_stock",
            "test_result":"offline_h264_aac_ffprobe_verified"}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--topic",required=True)
    parser.add_argument("--language",choices=("en","de"),default="en")
    parser.add_argument("--mode",choices=("short","long"),required=True)
    parser.add_argument("--out",required=True)
    args=parser.parse_args()
    print(json.dumps(make_video(
        topic=args.topic,language=args.language,mode=args.mode,
        output=args.out),ensure_ascii=False))


if __name__=="__main__":
    main()
