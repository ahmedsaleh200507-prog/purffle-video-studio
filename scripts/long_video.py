"""Experimental long-form documentary renderer. Shorts workflow remains untouched."""
import argparse, json, os, re, subprocess, math
from pathlib import Path
from types import SimpleNamespace

OUT = Path("long_video_output")
# B-roll varies by the documentary chapter rather than rotating randomly.
# Scenes must STILL pass a real-frame visual check; text metadata alone is weak.
LONG_CHAPTER_QUERIES = (
    "volcano eruption", "volcanic mountain tectonic plates", "molten lava",
    "lava flowing from volcano", "volcano gas plume", "explosive volcano eruption",
    "lava flow volcano", "volcano seismic monitoring", "volcano eruption smoke",
    "volcanic ash cloud", "lava river", "volcano crater",
    "volcanic landscape after eruption", "volcano aerial",
)
LONG_FALLBACK_QUERIES = ("volcano eruption", "lava flow", "volcano crater", "volcanic ash")
# Genuine modern glacier footage is illustrative of the environment, not
# footage of prehistoric events or scenes from a copyrighted animated film.
FIRE_AND_ICE_QUERIES = (
    "volcano under glacier iceland", "glacier mountain ice aerial",
    "volcano lava eruption", "volcanic lava icy mountain",
    "volcano steam eruption", "glacier ice cave",
    "glacier river flood", "iceland volcano eruption",
    "volcano volcanic ash cloud", "volcano smoke eruption",
    "glacier mountain aerial", "glacier ice sheet",
    "volcano crater aerial", "iceland volcanic mountain",
)
GLACIER_VISUAL_CHAPTERS = frozenset((1, 5, 6, 10, 11, 12))
GLACIER_FALLBACK_QUERIES = (
    "glacier ice mountain", "glacier aerial", "ice glacier",
    "snow glacier mountains", "glacier ice cave",
)


def long_expected_subject(index, topic, chapter=None):
    if isinstance(chapter, dict) and chapter.get("visual_subject"):
        return str(chapter["visual_subject"]).strip().lower()
    from long_script import is_fire_and_ice
    return ("glacier" if is_fire_and_ice(topic)
            and index % 14 in GLACIER_VISUAL_CHAPTERS else "volcano")





def long_visual_queries(index, topic="", chapter=None):
    """Language-neutral English stock keywords for the actual chapter subject."""
    if isinstance(chapter, dict) and chapter.get("visual_search_query"):
        requested = str(chapter["visual_search_query"]).strip()
        subject = str(chapter.get("visual_subject") or "").strip()
        # Search visible chapter subject with a few common real-video tags.
        # All returned footage still passes metadata and local CLIP checks.
        searches = [requested, subject]
        if subject and len(subject.split()) <= 3:
            searches += [subject + " nature", subject + " wildlife"]
        return list(dict.fromkeys(q for q in searches if q))
    from long_script import is_fire_and_ice
    if is_fire_and_ice(topic):
        selected = FIRE_AND_ICE_QUERIES[index % len(FIRE_AND_ICE_QUERIES)]
        fallback = (GLACIER_FALLBACK_QUERIES
                    if long_expected_subject(index, topic) == "glacier"
                    else LONG_FALLBACK_QUERIES)
    else:
        selected = LONG_CHAPTER_QUERIES[index % len(LONG_CHAPTER_QUERIES)]
        fallback = LONG_FALLBACK_QUERIES
    return list(dict.fromkeys((selected, *fallback)))


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


def chapters(topic, language="en"):
    from long_script import build_documentary
    # Preserve the proven English volcano workflow. Mixed-language jobs and
    # other documentary subjects receive genuinely topic-specific outlines.
    if language == "en" and any(
            term in topic.casefold() for term in ("volcano", "volcan", "lava")):
        return build_documentary(topic)
    from long_generic import build_multilingual_documentary
    return build_multilingual_documentary(topic, language)

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


def real_word_captions(speech, chapter_start):
    """Use the pinned upstream Word.text contract, not Whisper's raw Word.word.

    Strict validation here prevents the late AttributeError previously seen
    after spending several minutes producing private reference audio. Caption
    times are checked directly against real voice WAV samples; never guessed.
    """
    duration = float(speech.duration)
    if not math.isfinite(duration) or duration <= 0:
        raise RuntimeError("long_voice_contract: invalid recorded audio duration")
    raw_words = getattr(speech, "words", None)
    if not raw_words:
        raise RuntimeError("long_voice_contract: no aligned words")
    validated = []
    previous_end = 0.0
    for number, word in enumerate(raw_words, 1):
        text = getattr(word, "text", None)
        start = getattr(word, "start", None)
        end = getattr(word, "end", None)
        if not isinstance(text, str) or not text.strip():
            raise RuntimeError(
                f"long_voice_contract: word {number} missing required upstream Word.text")
        try:
            start, end = float(start), float(end)
        except (TypeError, ValueError) as exc:
            raise RuntimeError(
                f"long_voice_contract: word {number} lacks real timing") from exc
        if (not math.isfinite(start) or not math.isfinite(end)
                or start < -0.01 or start < previous_end - 0.08
                or end <= start or end > duration + 0.15):
            raise RuntimeError(
                f"long_voice_contract: word {number} timestamps are invalid")
        validated.append((text.strip(), max(0.0, start), end))
        previous_end = end
    captions = []
    for j in range(0, len(validated), 6):
        group = validated[j:j+6]
        captions.append((
            float(chapter_start) + group[0][1],
            float(chapter_start) + group[-1][2],
            " ".join(word[0] for word in group)
        ))
    return captions


def narrate(data,work,language="en"):
    if language not in ("en","de"):
        raise RuntimeError("Only English or German long documentaries are supported")
    from local_voice import synthesize as piper_synthesize
    audios, lines, offset=[],[],0.0
    for i,c in enumerate(data):
        text=c["narration"]
        speech=piper_synthesize(text,work/f"voice-{i+1}",SimpleNamespace(language=language))
        from studio_runtime import _validate_free_speech
        _validate_free_speech(speech, "piper", language)
        if (not Path(speech.audio).is_file() or not speech.words
                or not 20<=speech.duration<=110):
            raise RuntimeError(f"Chapter {i+1} {language} voice invalid")
        audios.append((Path(speech.audio),float(speech.duration)))
        lines.extend(real_word_captions(speech,offset))
        offset+=speech.duration
        print(f"[VOICE] language={language} chapter={i+1}/14 "
              f"seconds={speech.duration:.1f}",flush=True)
    if not 540<=offset<=660:
        raise RuntimeError(
            f"Real {language} narration duration={offset:.1f}s "
            "outside 9-11 min; no silent padding")
    return audios,lines,offset


def srt_time(t):
    ms=round(t*1000)
    h,ms=divmod(ms,3600000)
    m,ms=divmod(ms,60000)
    s,ms=divmod(ms,1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


# Only pre-existing, permission-screened real MP4 sources. No scraping,
# premium/synthetic material, bypassing missing Pexels credentials, or fake
# stock. Try Pixabay first; Wikimedia and NASA require no API keys.
LONG_STOCK_PROVIDERS = (
    "pixabay", "pexels", "wikimedia-video", "nasa-video",
    "coverr-video", "archive-video", "europeana-video", "nps-video",
    "usgs-video", "freenaturestock-video",
)


def confirm_long_stock_sources(registry):
    """Fail before narration if no known real-video provider is enabled.

    Pexels paused issuing new API keys in November 2026. A working Pixabay
    credential or an existing open public video catalog is sufficient.
    """
    ready = set(getattr(registry, "enabled", [])) & set(LONG_STOCK_PROVIDERS)
    if not ready:
        raise RuntimeError(
            "long_stock_preflight: no licensed real-video source available; "
            "enable Pixabay or public Wikimedia/NASA video catalogs")
    return sorted(ready)


def long_visual_verifier(path, metadata, need, *, matcher=None,
                         expected_subject="volcano", visual_query=None):
    """Reject mismatched real frames even when provider keywords say 'volcano'.

    This screening is only for 10-minute documentaries. Shorts keep their
    existing visual selection engine, untouched. Acceptable volcanic imagery
    must show an observable volcano, lava or ash; a road or bridge alone is not
    suitable footage for a volcano film.
    """
    from media_validation import SceneMatcher, SceneSpec, ValidationError
    matcher = matcher if matcher is not None else SceneMatcher(threshold=.22)
    details = str(metadata or "").casefold()
    if visual_query:
        subject, query = expected_subject, str(visual_query)
    elif expected_subject == "glacier":
        # Only real glacier footage; do not confuse general snow or a mountain
        # roadway with a continental ice sheet.
        subject, query = "glacier", "glacier ice mountain"
    elif "lava" in details or "magma" in details:
        subject, query = "lava", "molten lava flowing"
    elif "ash" in details and ("volcan" in details or "erupt" in details):
        subject, query = "volcano", "volcanic ash eruption plume"
    else:
        subject, query = "volcano", "volcano mountain eruption"
    spec = SceneSpec(main_character="", object=subject, action="ambient",
                     visual_search_query=query)
    try:
        result = matcher.match(path, spec, metadata=metadata, duration=need)
        result["visual_role"] = "direct_chapter_match"
    except ValidationError as exc:
        # An uploaded whale video can be tagged only "humpback whale", not
        # "humpback whale migration". Only metadata-missing actions may
        # fall back to illustrative B-roll of that exact visible subject.
        # Still require a complete subject match and real-frame CLIP proof.
        if not visual_query or "metadata" not in str(exc).lower():
            raise
        generic = SceneSpec(
            main_character="", object=subject, action="ambient",
            visual_search_query=subject)
        if SceneMatcher.metadata_score(generic, metadata) < 1.0:
            raise
        result = matcher.match(path, generic, metadata=metadata, duration=need)
        result["visual_role"] = "illustrative_subject_only"
    if result.get("verification") != "local_clip_screening":
        raise ValidationError("Long documentary visual-verifier proof missing")
    return result


def find_stock(index, chapter_seconds, seen, work, registry=None, topic="",
               bank=None, reused=None, chapter=None):
    """Pick real licensed HD footage: new sources first, verified unused spans last.

    A prior 10-minute Fire and Ice run failed at chapter 13 despite 12 fully
    rendered chapters: only Pixabay was enabled, 21 real-frame CLIP rejections
    occurred during 25 download attempts for the chapter, and the hard cap
    exhausted one query before testing the broader fallback terms.

    Spread a fixed candidate budget fairly across distinct search queries.
    After exhausting NEW clips, a source from another chapter may be reused
    ONCE, but only from a not-yet-played part of that same real video, and
    only after local CLIP re-verifies frames from that exact later segment.
    Reuse is explicitly recorded in credits. No static filler or blind reuse.
    """
    from media_validation import VideoDownloader, QualityValidator, reject_offtopic_science_source, download_hd_variant
    from video_sources import ProviderRegistry
    reg = registry if registry is not None else ProviderRegistry()
    dl = VideoDownloader(
        cache_dir=work/"downloads", max_bytes=175*1024*1024,
        max_cache_bytes=5*1024**3, min_free_bytes=2*1024**3,
    )
    val = QualityValidator(min_short_side=720)
    chosen, attempted = [], set()
    attempts, max_attempts, max_per_query, max_per_provider = 0, 60, 24, 3
    expected_subject = long_expected_subject(index, topic, chapter)
    from era_policy import scene_era, footage_allowed
    era = scene_era(chapter)
    for query in long_visual_queries(index, topic, chapter):
        query_attempts = 0
        for provider in LONG_STOCK_PROVIDERS:
            provider_attempts = 0
            try:
                candidates = reg.search(provider, query)[:40]
            except Exception as exc:
                print("[LONG PROVIDER UNAVAILABLE]", provider, type(exc).__name__, flush=True)
                continue
            for candidate in candidates:
                if provider_attempts >= max_per_provider:
                    break
                key = (candidate.source, str(candidate.id))
                if key in seen or key in attempted:
                    continue
                if not footage_allowed(provider, era, candidate.text, candidate.extra.get("recorded_date","")):
                    print("[LONG ERA REJECT]",provider,candidate.id,flush=True)
                    continue
                labels = candidate.text.lower()
                if chapter and chapter.get("visual_subject"):
                    terms = tuple(x for x in expected_subject.split()
                                  if len(x) >= 3)
                else:
                    terms = (("glacier", "glacial", "ice sheet")
                             if expected_subject == "glacier"
                             else ("volcan", "lava", "magma", "eruption", "crater"))
                if not any(term in labels for term in terms):
                    continue
                if query_attempts >= max_per_query or attempts >= max_attempts:
                    break
                attempted.add(key)
                query_attempts += 1
                provider_attempts += 1
                attempts += 1
                try:
                    reject_offtopic_science_source(topic, candidate.text)
                    path, q = download_hd_variant(candidate, dl, val,
                        segment_seconds=max(15.,chapter_seconds/3+1),
                        check=lambda x: int(x["width"]) >= 1280 and int(x["height"]) >= 720)
                    duration = float(q["duration"])
                    if (int(q["width"]) < 1280 or int(q["height"]) < 720
                            or duration * 1.5 < chapter_seconds / 4):
                        continue
                    visual_span = min(duration, chapter_seconds / 3)
                    if chapter and chapter.get("visual_search_query"):
                        visual = long_visual_verifier(
                            path,candidate.text,visual_span,
                            expected_subject=expected_subject,
                            visual_query=chapter["visual_search_query"])
                    else:
                        visual = long_visual_verifier(
                            path,candidate.text,visual_span,
                            expected_subject=expected_subject)
                    lic = candidate.extra["license"]
                    credit = {
                        "source": candidate.source, "id": candidate.id,
                        "creator": lic["creator"], "license": lic["id"],
                        "license_url": lic["url"],
                        "attribution_required": bool(lic.get("attribution_required")),
                        "source_page": lic["source_page"], "query": query,
                        "metadata_text": str(candidate.text)[:400],
                        "recorded_date": candidate.extra.get("recorded_date",""),
                        "era_policy": era,
                        "subject": expected_subject, "chapter": index+1,
                        "visual_check": visual["verification"],
                        "visual_score": visual.get("visual_score"),
                        "visual_role": visual.get("visual_role", "direct_chapter_match"),
                        "download_evidence": candidate.extra.get("download_evidence", {"mode":"full_download"}),
                        "reused": False, "source_offset_seconds": 0.0,
                    }
                    seen.add(key)
                    chosen.append((path, duration, credit))
                    if len(chosen) >= 4:
                        return chosen
                except Exception as ex:
                    # Include bounded diagnostic reason, not provider tokens/URLs.
                    print("[LONG STOCK REJECT]", type(ex).__name__,
                          str(ex).splitlines()[0][:160], flush=True)
            if query_attempts >= max_per_query or attempts >= max_attempts:
                break
        if attempts >= max_attempts:
            break
    # 3 clips each need enough unique motion for their chapter share.
    usable = [c for c in chosen
              if c[1] * 1.5 >= chapter_seconds / 3]
    if len(usable) >= 3:
        return usable[:3]

    # The previously validated source bank is restricted to the same visual
    # subject, distinct clips, and UNUSED footage from each original source.
    # This fallback must not silently weaken local CLIP image matching.
    bank = bank if bank is not None else []
    reused = reused if reused is not None else set()
    recoveries = []
    for old_path, old_duration, old_credit in reversed(bank):
        if len(usable) + len(recoveries) >= 3:
            break
        if old_credit.get("subject") != expected_subject:
            continue
        if not footage_allowed(old_credit["source"],era,old_credit.get("metadata_text",""),old_credit.get("recorded_date","")):
            continue
        key = (old_credit["source"], str(old_credit["id"]))
        if key in reused or any(
                (c[2]["source"], str(c[2]["id"])) == key for c in usable):
            continue
        offset = float(old_credit.get("source_end_seconds", old_duration))
        remaining = float(old_duration) - offset
        if remaining * 1.5 < chapter_seconds / 3 or remaining <= 0:
            continue
        preview = work/"reuse_previews"/(
            f"chapter-{index+1:02d}-{len(recoveries)}.mp4")
        preview.parent.mkdir(parents=True, exist_ok=True)
        segment_length = min(remaining, chapter_seconds / 3)
        try:
            run(["ffmpeg", "-hide_banner", "-nostdin", "-y", "-loglevel", "error",
                 "-ss", f"{offset:.3f}", "-i", str(old_path),
                 "-t", f"{segment_length:.3f}", "-an",
                 "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
                 str(preview)], 180)
            # The unused section must itself still contain genuine moving HD
            # frames. Validating the entire original source is not sufficient.
            preview_quality = val.validate(preview)
            if (int(preview_quality["width"]) < 1280
                    or int(preview_quality["height"]) < 720
                    or float(preview_quality["duration"]) < segment_length - .5):
                raise RuntimeError("Unused stock portion lacks required HD motion or duration")
            if chapter and chapter.get("visual_search_query"):
                proof = long_visual_verifier(
                    preview,old_credit["metadata_text"],segment_length,
                    expected_subject=expected_subject,
                    visual_query=chapter["visual_search_query"])
            else:
                proof = long_visual_verifier(
                    preview,old_credit["metadata_text"],segment_length,
                    expected_subject=expected_subject)
            credit = {
                **old_credit,
                "chapter": index+1, "reused": True,
                "reused_from_chapter": old_credit["chapter"],
                "source_offset_seconds": round(offset, 3),
                "visual_check": proof["verification"],
                "visual_score": proof.get("visual_score"),
                "visual_role": proof.get("visual_role", "direct_chapter_match"),
            }
            recoveries.append((old_path, old_duration, credit))
        except Exception as ex:
            print("[LONG STOCK UNUSED SPAN REJECT]", type(ex).__name__,
                  str(ex).splitlines()[0][:160], flush=True)
        finally:
            preview.unlink(missing_ok=True)
    if len(usable) + len(recoveries) >= 3:
        selected = (usable + recoveries)[:3]
        for item in selected:
            if item[2].get("reused"):
                reused.add((item[2]["source"], str(item[2]["id"])))
        print(f"[LONG STOCK SELECT] chapter={index+1} new="
              f"{sum(not x[2]['reused'] for x in selected)} "
              f"verified_unused_spans={sum(x[2]['reused'] for x in selected)} "
              f"tried={attempts}", flush=True)
        return selected

    # A last alternative is two distinct new sources, but never slow them
    # more than 1.5x and never fill missing footage by freezing frames.
    pairs = [c for c in usable if c[1] * 1.5 >= chapter_seconds / 2]
    if len(pairs) >= 2:
        return pairs[:2]

    # Completion-first, still real footage: a single sufficiently LONG
    # independently licensed, HD, moving and CLIP-screened video can cover
    # this chapter without black filler, fabricated stock or frame freezes.
    # Less varied visually than three shots, but safer than discarding the
    # entire ten-minute documentary after a successful real-clip match.
    single = next((c for c in sorted(
        chosen, key=lambda c: c[1], reverse=True)
        if c[1] * 1.5 >= chapter_seconds), None)
    if single is not None:
        print(f"[LONG STOCK SINGLE CLIP] chapter={index+1} "
              f"licensed_clips=1 source_duration={single[1]:.1f}s "
              "subject_verified=True", flush=True)
        single[2]["completion_fallback"] = "one_verified_long_moving_clip"
        return [single]
    raise RuntimeError(
        f"long_stock_insufficient_chapter_{index+1}: "
        f"{len(usable)} new usable clips, {len(recoveries)} independently "
        f"verified unused stock spans (tried={attempts}); need 3 distinct "
        "usable segments or 2 long distinct clips. "
        "No off-topic or unverified clips accepted.")


def render_scene(i,audio,duration,stock,work):
    shotdir=work/f"shots-{i:02d}"
    shotdir.mkdir(parents=True,exist_ok=True)
    files=[]
    wanted=duration/len(stock)
    for j,(path,srcdur,credit) in enumerate(stock):
        offset=float(credit.get("source_offset_seconds", 0))
        available=srcdur-offset
        if available <= 0:
            raise RuntimeError("Verified footage has no unused motion")
        factor=max(1.0,wanted/available)
        if factor>1.5:
            raise RuntimeError("Insufficient real motion for scene")
        dest=shotdir/f"shot-{j:02d}.mp4"
        vf=(f"setpts={factor:.6f}*(PTS-STARTPTS),"
            "scale=1920:1080:force_original_aspect_ratio=increase,"
            "crop=1920:1080,fps=30,format=yuv420p")
        run(["ffmpeg","-hide_banner","-nostdin","-y","-loglevel","error",
             "-ss",f"{offset:.3f}","-i",str(path),"-t",f"{wanted:.3f}",
             "-an","-vf",vf,
             "-c:v","libx264","-preset","veryfast","-crf","25",str(dest)],900)
        # Keep precise source ranges for safe later B-roll reuse.
        credit["source_end_seconds"]=round(min(srcdur,offset+wanted/factor),3)
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
    # Keep original timed captions as a *separate optional SRT file*, never
    # as a default or burned-in MP4 subtitle stream. Some FFmpeg/MP4 muxers
    # re-enable disposition=default even when explicitly passed "0".
    if not Path(subtitles).is_file():
        raise RuntimeError("Long documentary SRT sidecar is missing")
    manifest=work/"all-scenes.txt"
    manifest.write_text("\n".join("file '"+str(x.resolve())+"'" for x in scene_paths)+"\n")
    stitched=work/"stitched.mp4"
    run(["ffmpeg","-hide_banner","-nostdin","-y","-loglevel","error",
         "-f","concat","-safe","0","-i",str(manifest),"-c","copy",str(stitched)],1500)
    run(["ffmpeg","-hide_banner","-nostdin","-y","-loglevel","error",
         "-i",str(stitched),"-map","0:v:0","-map","0:a:0","-c:v","copy",
         "-af","loudnorm=I=-17:TP=-1.5:LRA=11","-c:a","aac","-b:a","192k",
         "-movflags","+faststart",str(target)],1500)


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--topic",default="Why do volcanoes erupt?")
    p.add_argument("--language",choices=("en","de"),default="en")
    p.add_argument("--self-test",action="store_true")
    a=p.parse_args()
    if a.self_test:
        assert srt_time(60.53)=="00:01:00,530"
        assert words("Volcanoes can erupt suddenly.")==4
        fake_voice = SimpleNamespace(
            duration=1.0,
            words=[
                SimpleNamespace(text="Volcanoes", start=.10, end=.44),
                SimpleNamespace(text="erupt.", start=.47, end=.83),
            ],
        )
        sample = real_word_captions(fake_voice, 4.0)
        assert len(sample) == 1 and sample[0][2] == "Volcanoes erupt."
        assert sample[0][0] == 4.1 and sample[0][1] == 4.83
        print("Static long-video tests passed")
        return
    from long_generic import check_long_topic
    a.topic = check_long_topic(a.topic, a.language)
    output,work=OUT/"result",OUT/"work"
    output.mkdir(parents=True,exist_ok=True)
    work.mkdir(parents=True,exist_ok=True)
    report={"mode":"long_video","status":"failed","mp4":None,"topic":a.topic,
            "language":a.language,"target_duration":600,"resolution":"1920x1080"}
    stage="preflight"
    try:
        from english_reference_policy import enforce_english_reference_only
        if a.language == "en":
            enforce_english_reference_only("en")
        stage="long_stock_preflight"
        from video_sources import ProviderRegistry
        registry = ProviderRegistry()
        try:
            print("[LONG SOURCES READY]", confirm_long_stock_sources(registry), flush=True)
        except RuntimeError as exc:
            print("[LONG SOURCES FALLBACK]", str(exc), flush=True)
        stage="script"
        text=chapters(a.topic,a.language)
        from long_quality_gate import verify_narration
        preliminary_qa=verify_narration(text,a.language)
        save(output/"script.json",{"language":a.language,"chapters":text})
        save(output/"script-quality.json",preliminary_qa)
        stage="fixed_piper_voice"
        audio,subs,voice_seconds=narrate(text,work,a.language)
        with (output/"captions.srt").open("w",encoding="utf8") as f:
            for j,(start,end,line) in enumerate(subs,1):
                f.write(f"{j}\n{srt_time(start)} --> {srt_time(end)}\n{line}\n\n")
        stage="real_stock"
        used,scenes,credits=set(),[],[]
        from long_still_recovery import render_recovery
        stock_bank, reused_source_ids = [], set()
        still_ids, recovery_chapters = set(), []
        for i,(wav,seconds) in enumerate(audio):
            try:
                clips=find_stock(i,seconds,used,work,registry=registry,topic=a.topic,
                                 bank=stock_bank,reused=reused_source_ids,chapter=text[i])
                stage=f"render_chapter_{i+1}"
                scenes.append(render_scene(i+1,wav,seconds,clips,work))
                stock_bank.extend(c for c in clips if not c[2].get("reused"))
                credits.extend(c[2] for c in clips)
            except Exception as exc:
                print("[LONG CHAPTER RECOVERY]", i+1, type(exc).__name__, flush=True)
                stage=f"recover_chapter_{i+1}"
                scene, recovery_credits=render_recovery(
                    i+1,wav,seconds,text[i],work,still_ids,run)
                scenes.append(scene)
                credits.extend(recovery_credits)
                recovery_chapters.append(i+1)
            print(f"[RENDER] {i+1}/14",flush=True)
            stage="real_stock"
        save(output/"credits.json",credits)
        stage="final_mp4"
        final=output/"long-video.mp4"
        finish(scenes,output/"captions.srt",final,work)
        duration,width,height,audible=probe(final)
        if not (540<=duration<=660 and width==1920 and height==1080 and audible):
            raise RuntimeError("Final video failed measured duration/1080p/audio validation")
        report.update(status="review",mp4="long-video.mp4",duration=duration,
                      recovery_chapters=recovery_chapters)
        stage="full_timeline_qa"
        from output_qa import validate_timeline
        full_qa=validate_timeline(final,output/"captions.srt",
            expected_size=(1920,1080),expected_duration=voice_seconds,
            expected_text=' '.join(c['narration'] for c in text))
        save(output/"output-qa.json",full_qa)
        save(output/"credits.json",credits)
        from long_quality_gate import verify_finished
        publishing_qa=({**preliminary_qa,
            "publication_quality":"review_mixed_media",
            "photo_uses":sum(c.get("media_type")=="photo" for c in credits),
            "illustration_uses":sum(c.get("media_type")=="illustration" for c in credits),
            "recovery_chapters":recovery_chapters}
            if recovery_chapters else verify_finished(final,text,credits,language=a.language))
        save(output/"documentary-quality.json",publishing_qa)
        report.update(status="review" if recovery_chapters else "ok",mp4="long-video.mp4",duration=duration,
                      clips=len(credits),narration_duration=voice_seconds,
                      reused_unused_segments=sum(bool(c.get("reused")) for c in credits),
                      new_unique_sources=len({
                          (c["source"], str(c["id"])) for c in credits
                          if not c.get("reused")
                      }),
                      audio_target_lufs=-17,
                      burnt_in_subtitles=False,
                      subtitle_track="separate_srt_sidecar_only",
                      visual_verification="mixed_media_review" if recovery_chapters else "local_clip_screening",
                      illustrative_subject_clips=sum(
                          c.get("visual_role") == "illustrative_subject_only" for c in credits),
                      note=("Contains licensed photos or marked original illustrations; review before publishing." if recovery_chapters else "All clips pass metadata + local CLIP screening. Illustrative B-roll is not exact footage of narrated events."))
    except Exception as e:
        report.update(stage=stage,error=(type(e).__name__+": "+str(e))[:800])
        # A fixed 602-second file with seven repeated sentences is NOT
        # a valid documentary. Do not silently turn errors into fake success.
        # The workflow will preserve any independently screened real footage
        # chapters and report the original cause honestly.
        raise
    finally:
        save(output/"report.json",report)


if __name__=="__main__":
    main()
