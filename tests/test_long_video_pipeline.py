"""Real pipeline contracts for the isolated 10-minute workflow.

No private voice sample, real API, or external stock clip is used in tests.
Synthetic media proves actual FFmpeg output mechanics, never production quality.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import json
import math
import os
import shutil
import wave

import pytest

from long_video import (
    real_word_captions, narrate, srt_time, render_scene, finish, probe,
    find_stock, confirm_long_stock_sources, long_visual_verifier, long_visual_queries, long_expected_subject,
)


def fake_speech(*, fields="text", duration=43):
    word_factory = lambda w,s,e: SimpleNamespace(**{
        fields: w, "start": s, "end": e,
    })
    return SimpleNamespace(duration=duration, words=[
        word_factory("Volcanoes", 0.1, 0.5),
        word_factory("erupt.", 0.6, 1.0),
        word_factory("Molten", 1.2, 1.7),
        word_factory("rock", 1.8, 2.1),
    ])


def test_word_text_is_source_of_truth_for_private_english_voice_captions():
    # From the pinned upstream purffle_shorts.timing.Word: .text not .word.
    speech = fake_speech()
    assert real_word_captions(speech, 60) == [
        (60.1, 62.1, "Volcanoes erupt. Molten rock")
    ]
    assert srt_time(62.1) == "00:01:02,100"


def test_word_word_property_bug_now_produces_early_actionable_contract_error():
    with pytest.raises(RuntimeError, match="Word.text"):
        real_word_captions(fake_speech(fields="word"), 0)


def test_invalid_or_fabricated_timestamps_are_rejected():
    speech = fake_speech()
    speech.words[2].start = float("nan")
    with pytest.raises(RuntimeError, match="timestamps are invalid"):
        real_word_captions(speech, 0)
    speech = fake_speech()
    speech.words[3].end = 44
    with pytest.raises(RuntimeError, match="timestamps are invalid"):
        real_word_captions(speech, 0)


def test_pinned_upstream_word_has_text():
    timing = pytest.importorskip("purffle_shorts.timing")
    word = timing.Word("lava", .2, .6)
    assert word.text == "lava"
    assert real_word_captions(SimpleNamespace(duration=1., words=[word]), 0)[0][2] == "lava"


def test_all_fourteen_chapters_preserve_voice_word_contract(tmp_path, monkeypatch):
    # Simulate the approved voice output, not voice synthesis itself:
    # verifies the FULL 14-chapter speech -> timeline -> caption interaction.
    voice = pytest.importorskip("approved_reference_voice")
    policy = pytest.importorskip("english_reference_policy")
    monkeypatch.setattr(policy, "enforce_english_reference_only", lambda lang: None)

    def fake_synthesize(text, output, settings, *, segments, long_form=False):
        assert long_form and settings.language == "en"
        assert 2 <= len(segments) <= 6 and " ".join(segments) == text
        path = Path(output) / "approved-generated.wav"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"test fixture: simulated reference WAV")
        data = fake_speech(duration=43)
        data.audio = path
        return data

    monkeypatch.setattr(voice, "synthesize", fake_synthesize)
    chapter = {"narration": (
        "Volcanoes arise when rock melts deep inside the Earth. "
        "The resulting magma may slowly rise towards the ground. "
        "Gases trapped in the rock help create pressure. "
        "A sudden burst of pressure can cause eruptions."
    )}
    output, captions, seconds = narrate([chapter] * 14, tmp_path)
    assert len(output) == 14 and len(captions) == 14
    assert seconds == 602.
    assert captions[0][0] == .1
    assert captions[-1][0] > 540


def test_long_stock_credentials_checked_before_expensive_voice():
    with pytest.raises(RuntimeError, match="long_stock_preflight"):
        confirm_long_stock_sources(SimpleNamespace(enabled=["wikimedia-video"]))
    assert confirm_long_stock_sources(
        SimpleNamespace(enabled=["pixabay", "pexels", "nasa-video"])
    ) == ["pexels", "pixabay"]


def test_stock_fallback_keeps_three_distinct_real_sources_without_faking(monkeypatch, tmp_path):
    pytest.importorskip("PIL")
    import media_validation
    items = [
        SimpleNamespace(source="pixabay", id=i, text="Real volcano eruption lava closeup",
                        url=f"https://example.org/{i}.mp4",
                        extra={"license": {
                            "creator": "Stock contributor", "id": "PIXABAY",
                            "source_page": f"https://pixabay.com/{i}",
                        }})
        for i in range(3)
    ]
    class FakeRegistry:
        def search(self, provider, query):
            return items if provider == "pixabay" else []
    def fake_download(self, url):
        return tmp_path / url.rsplit("/", 1)[-1]
    monkeypatch.setattr(media_validation.VideoDownloader, "download", fake_download)
    monkeypatch.setattr(media_validation.QualityValidator, "validate",
                        lambda self, path: {"width": 1920, "height": 1080, "duration": 30.0})
    # This test isolates source selection, not the real CLIP inference.
    import long_video
    monkeypatch.setattr(long_video, "long_visual_verifier",
                        lambda *args, **kwargs: {
                            "verification":"local_clip_screening","visual_score":0.30})
    seen=set()
    selected=find_stock(0,45,seen,tmp_path,registry=FakeRegistry())
    assert len(selected)==3
    assert len(seen)==3
    assert len({x[2]["id"] for x in selected})==3


def test_long_only_storyboard_prioritizes_correct_chapter_queries():
    assert long_visual_queries(2)[0] == "molten lava"
    assert long_visual_queries(9)[0] == "volcanic ash cloud"
    assert long_visual_queries(11)[0] == "volcano crater"
    assert len(long_visual_queries(0)) == len(set(long_visual_queries(0)))


def test_long_visual_verifier_rejects_wrong_frames_even_with_volcano_metadata():
    from media_validation import ValidationError
    class FakeMatcher:
        def match(self, path, spec, metadata, duration):
            assert spec.object == "volcano"
            assert spec.action == "ambient"
            assert "volcano" in metadata.lower()
            raise ValidationError("CLIP rejected road or bridge footage")
    with pytest.raises(ValidationError, match="road or bridge"):
        long_visual_verifier(
            Path("unrelated-bridge.mp4"), "Volcano travel road bridge",
            12.0, matcher=FakeMatcher())


def test_long_visual_verifier_accepts_only_real_clip_screening():
    from media_validation import ValidationError
    class FakeMatcher:
        def match(self, path, spec, metadata, duration):
            assert spec.object == "lava" and "lava" in spec.visual_search_query
            return {"verification": "metadata_only"}
    with pytest.raises(ValidationError, match="proof missing"):
        long_visual_verifier(
            Path("unverified.mp4"), "molten lava flow",
            12.0, matcher=FakeMatcher())


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
                    reason="FFmpeg required for real render contract")
def test_ffmpeg_renders_narrated_chapter_with_sidecar_only_subtitles(tmp_path):
    from long_video import run
    src = tmp_path / "test-footage.mp4"
    wav = tmp_path / "voice.wav"
    run(["ffmpeg","-hide_banner","-loglevel","error","-y",
         "-f","lavfi","-i","testsrc2=size=1280x720:rate=30",
         "-t","2.5","-c:v","libx264","-preset","ultrafast",str(src)],60)
    with wave.open(str(wav),"wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(16000)
        # A real narrator is audible; fully silent PCM makes FFmpeg loudnorm
        # compute undefined loudness and is not a valid normalisation fixture.
        import math, struct
        f.writeframes(b"".join(
            struct.pack("<h", int(1500 * math.sin(2 * math.pi * 220 * t / 16000)))
            for t in range(16000 * 2)
        ))
    media=[(src,2.5,{"source":"synthetic-test-only"})]
    chapter=render_scene(1,wav,2.0,media,tmp_path)
    assert chapter.is_file()
    # Subtitles live in a separate selectable MP4 track as in production.
    captions=tmp_path/"captions.srt"
    captions.write_text("1\n00:00:00,100 --> 00:00:01,700\nSynthetic footage test\n",encoding="utf-8")
    final=tmp_path/"contract.mp4"
    finish([chapter],captions,final,tmp_path)
    assert final.is_file()
    seconds,width,height,audio=probe(final)
    assert 1.8 <= seconds <= 2.3 and (width,height)==(1920,1080) and audio
    from long_video import run
    streams=json.loads(run(["ffprobe","-v","error","-show_streams","-of","json",str(final)],60))["streams"]
    # MP4 must not show text by default on any player; YouTube can accept
    # the independently generated SRT when captions are desired.
    assert captions.read_text().startswith("1\\n".replace("\\n", "\n"))
    assert not any(stream["codec_type"] == "subtitle" for stream in streams)
    audio_streams = [stream for stream in streams if stream["codec_type"] == "audio"]
    assert audio_streams[0]["codec_name"] == "aac"


def test_fire_and_ice_documentary_has_expected_snow_and_volcanic_shots():
    topic = "Ice Age vs Lava: What Happens When a Volcano Erupts Beneath a Glacier?"
    assert long_expected_subject(1, topic) == "glacier"
    assert long_expected_subject(5, topic) == "glacier"
    assert long_expected_subject(6, topic) == "glacier"
    assert long_expected_subject(10, topic) == "glacier"
    assert long_expected_subject(12, topic) == "glacier"
    assert long_expected_subject(0, topic) == "volcano"
    assert long_expected_subject(9, topic) == "volcano"
    assert "glacier" in long_visual_queries(1, topic)[0]
    assert "volcano" in long_visual_queries(7, topic)[0]
    assert "glacier" in long_visual_queries(1, topic)[1]


def test_fire_and_ice_mismatched_glacier_frames_are_rejected():
    from media_validation import ValidationError
    class FakeMatcher:
        def match(self, path, spec, metadata, duration):
            assert spec.object == "glacier"
            assert "glacier" in spec.visual_search_query
            raise ValidationError("wrong glacier scene")
    with pytest.raises(ValidationError, match="wrong glacier scene"):
        long_visual_verifier(
            Path("city-road.mp4"), "Glacier aerial",
            12., matcher=FakeMatcher(), expected_subject="glacier")


def test_fire_and_ice_requires_glacier_in_provider_title(monkeypatch, tmp_path):
    import media_validation
    import long_video
    calls = []
    candidates = [
        SimpleNamespace(source="pixabay", id=i, text=title,
                        url=f"https://example.org/{i}.mp4",
                        extra={"license":{"creator":"Provider","id":"PIXABAY",
                                          "source_page":f"https://pixabay.com/{i}"}})
        for i,title in enumerate(("river bridge", "glacier mountain",
                                  "glacier ice", "glacial ice sheet"), 1)
    ]
    class Registry:
        def search(self, provider, query):
            return candidates if provider=="pixabay" else []
    monkeypatch.setattr(media_validation.VideoDownloader, "download",
                        lambda self, url: tmp_path/url.rsplit("/",1)[-1])
    monkeypatch.setattr(media_validation.QualityValidator, "validate",
                        lambda self,path:{"width":1920,"height":1080,"duration":30.})
    def verified(path, meta, need, *, expected_subject="volcano"):
        calls.append(expected_subject)
        assert "glaci" in meta.lower()
        return {"verification":"local_clip_screening","visual_score":0.31}
    monkeypatch.setattr(long_video, "long_visual_verifier", verified)
    result = find_stock(1, 45., set(), tmp_path, registry=Registry(),
                        topic="Ice Age vs Lava: Volcano Beneath a Glacier")
    assert len(result)==3
    assert len(calls)==3
    assert all(x=="glacier" for x in calls)
    assert all("bridge" not in c[2]["query"].lower() for c in result)


def test_stock_search_fairly_reaches_broad_query_after_initial_rejections(monkeypatch, tmp_path):
    """Regression: 25 bad stock candidates on one query no longer stop chapter 13."""
    import media_validation
    import long_video
    from media_validation import ValidationError
    topic = "Ice Age vs Lava: What Happens When a Volcano Erupts Beneath a Glacier?"
    searches = []
    def item(i, title="Glacier ice mountain"):
        return SimpleNamespace(
            source="pixabay", id=i, text=title,
            url=f"https://example.org/{i}.mp4",
            extra={"license":{"creator":"Contributor","id":"PIXABAY",
                              "source_page":f"https://pixabay.com/{i}"}})
    class Registry:
        def search(self, provider, query):
            if provider != "pixabay":
                return []
            searches.append(query)
            if query == long_video.long_visual_queries(12,topic)[0]:
                return [item(i) for i in range(25)]
            return [item(100+i) for i in range(4)]
    monkeypatch.setattr(media_validation.VideoDownloader, "download",
                        lambda self,url:tmp_path/url.rsplit("/",1)[-1])
    monkeypatch.setattr(media_validation.QualityValidator, "validate",
                        lambda self,path:{"width":1920,"height":1080,"duration":30})
    seen_paths=[]
    def verify(path, meta, length, *, expected_subject="volcano"):
        seen_paths.append(path.stem)
        if int(path.stem) < 100:
            raise ValidationError("Visual scene mismatch")
        assert expected_subject == "glacier"
        return {"verification":"local_clip_screening","visual_score":.36}
    monkeypatch.setattr(long_video,"long_visual_verifier",verify)
    chosen = find_stock(12, 43.0, set(), tmp_path, registry=Registry(), topic=topic)
    assert len(chosen) == 4
    assert len(set(searches)) >= 2
    assert sum(1 for p in seen_paths if int(p) < 100) == 12
    assert all(c[2]["id"] >= 100 for c in chosen)


def test_stock_bank_only_uses_newly_reverified_unplayed_spans(monkeypatch, tmp_path):
    """A last-resort repeat must be a DIFFERENT offset, verified as a real clip."""
    import long_video
    topic = "Ice Age vs Lava: What Happens When a Volcano Erupts Beneath a Glacier?"
    class Registry:
        def search(self, provider, query):
            return []
    bank=[]
    for i in range(3):
        path = tmp_path/f"original-{i}.mp4"
        path.write_bytes(b"synthetic video stub; never pass into real decoder")
        bank.append((path,40.0,{
            "source":"pixabay", "id":i, "source_page":f"https://pixabay.com/{i}",
            "creator":"Contributor", "license":"PIXABAY",
            "metadata_text":"Glacier ice mountain",
            "subject":"glacier","chapter":i+1,"reused":False,
            "source_end_seconds":11.0,
        }))
    seek_positions=[]
    def fake_run(args, timeout=1800):
        assert "-ss" in args
        seek_positions.append(float(args[args.index("-ss")+1]))
        Path(args[-1]).write_bytes(b"preview frame container placeholder")
        return ""
    def verifier(path,metadata,need,*,expected_subject="volcano"):
        assert path.is_file() and "Glacier" in metadata
        assert expected_subject=="glacier"
        return {"verification":"local_clip_screening","visual_score":.33}
    monkeypatch.setattr(long_video,"run",fake_run)
    monkeypatch.setattr(long_video,"long_visual_verifier",verifier)
    reused=set()
    chosen=find_stock(12, 42.0,set(),tmp_path,registry=Registry(),
                      topic=topic,bank=bank,reused=reused)
    assert len(chosen)==3 and len(reused)==3
    assert seek_positions==[11.0,11.0,11.0]
    assert all(x[2]["reused"] and x[2]["source_offset_seconds"]==11.0
               and x[2]["reused_from_chapter"] in (1,2,3)
               for x in chosen)


def test_stock_bank_rejects_unrelated_repeats_and_exhausted_sources(tmp_path):
    topic="Ice Age vs Lava: Volcano Beneath a Glacier"
    class Registry:
        def search(self,provider,query):
            return []
    bank=[(tmp_path/"old.mp4",20.0, {
        "source":"pixabay","id":77,"subject":"volcano",
        "source_end_seconds":18.0,"chapter":3,
    })]
    with pytest.raises(RuntimeError,match="long_stock_insufficient_chapter_13"):
        find_stock(12,43,set(),tmp_path,registry=Registry(),
                   topic=topic,bank=bank,reused=set())


def test_renderer_respects_separate_real_source_offset(monkeypatch,tmp_path):
    import long_video
    observed=[]
    def fake_run(args, timeout=1800):
        observed.append(args)
        return ""
    monkeypatch.setattr(long_video,"run",fake_run)
    credit={"reused":True,"source_offset_seconds":8.0}
    source=tmp_path/"real-media-original.mp4"
    audio=tmp_path/"approved-voice.wav"
    render_scene(13,audio,12.0,[(source,30.0,credit)],tmp_path)
    assert "-ss" in observed[0]
    assert float(observed[0][observed[0].index("-ss")+1]) == 8.0
    assert credit["source_end_seconds"] == 20.0
