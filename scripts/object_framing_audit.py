"""Actual model inference on a known example; not a footage accuracy benchmark."""
import io
import json
from pathlib import Path
import requests
from PIL import Image
from object_framing import detect, MODEL, REVISION, track_focus, best_object_window
import hashlib
import subprocess
import tempfile
from media_validation import _frame

# Hugging Face documentation's known cat fixture. HTTPS verification stays enabled.
FIXTURES = (
    "https://huggingface.co/datasets/huggingface/documentation-images/resolve/main/coco_sample.png",
    "https://huggingface.co/datasets/hf-internal-testing/fixtures-coco/resolve/main/coco_panoptic/000000039769.png",
)

def load_fixture():
    errors = []
    for url in FIXTURES:
        try:
            with requests.get(url, timeout=(10, 30), stream=True) as response:
                response.raise_for_status()
                data = bytearray()
                for chunk in response.iter_content(65536):
                    data.extend(chunk)
                    if len(data) > 5 * 1024 * 1024:
                        raise ValueError("Fixture too large")
            with Image.open(io.BytesIO(data)) as im:
                return im.convert("RGB"), url
        except (requests.RequestException, OSError, ValueError) as exc:
            errors.append(f"{url}: {type(exc).__name__}: {exc}")
    raise RuntimeError("No real test fixture available: " + "; ".join(errors))

# OpenCV's public pedestrian test sample, used only for evaluation.
# The Git blob digest binds the bytes to the inspected repository revision.
VIDEO_URL = "https://raw.githubusercontent.com/opencv/opencv/4.12.0/samples/data/vtest.avi"
VIDEO_SHA = "965ab12bdb5e498297cefb476e4efb8204c6a29a"

def real_video_audit():
    with tempfile.TemporaryDirectory() as temp:
        path=Path(temp)/"pedestrians.avi"
        with requests.get(VIDEO_URL, timeout=(15,45), stream=True) as r:
            r.raise_for_status()
            size=0
            with path.open("wb") as fp:
                for chunk in r.iter_content(65536):
                    size+=len(chunk)
                    if size>16*1024*1024:
                        raise ValueError("Video test fixture exceeds download bound")
                    fp.write(chunk)
        digest=hashlib.sha1()
        digest.update(f"blob {size}\\0".encode())
        with path.open("rb") as fp:
            for chunk in iter(lambda:fp.read(65536),b""):
                digest.update(chunk)
        if digest.hexdigest()!=VIDEO_SHA:
            raise ValueError("Unexpected video fixture bytes")
        meta=json.loads(subprocess.check_output(
            ["ffprobe","-v","error","-select_streams","v:0","-show_entries",
             "stream=width,height:format=duration","-of","json",str(path)],timeout=20))
        duration=float(meta["format"]["duration"])
        stream=meta["streams"][0]
        fraction=min(1.,stream["height"]*9/(stream["width"]*16))
        # Bounded CPU test: one inference per second over the first eight seconds.
        end=min(8.,duration-.2)
        if end<4:
            raise ValueError("Video fixture too short")
        times=[float(i) for i in range(int(end)+1)]
        rows=[detect(_frame(path,t,640,preserve_aspect=True),"person") for t in times]
        detected=sum(bool(row) for row in rows)
        result={"fixture":VIDEO_URL,"sha":VIDEO_SHA,"source_dimensions":[stream["width"],stream["height"]],
                "sample_times":times,"detections":rows,"detected_frames":detected,
                "tracking":track_focus(rows,times,fraction),
                "window":best_object_window(rows,times,times[-1],3.),
                "pass":detected>=2,
                "scope":"real decoded video inference; no human labels, identity or action accuracy measured; no production rendering"}
        return result

def main():
    out = Path("object-framing-audit")
    out.mkdir(exist_ok=True)
    result = {"model": MODEL, "revision": REVISION, "pass": False,
              "scope": "real photo inference smoke; not production footage validation",
              "stage": "fixture_download"}
    try:
        frame, url = load_fixture()
        result.update(fixture=url, stage="model_inference")
        cats = detect(frame, "cat")
        result["detections"] = cats
        if not cats:
            raise RuntimeError("Expected a visible cat in the documented test fixture")
        result["stage"] = "tracking_geometry"
        def obj(x, score=.9):
            return {"box":[x-.05,.3,x+.05,.65],"score":score}
        times = [0.,1.,2.,3.,4.]
        rows = [[obj(x)] for x in (.15,.30,.50,.70,.85)]
        track = track_focus(rows,times,.32)
        missing = track_focus([rows[0],[],*rows[2:]],times,.32)
        ambiguous = track_focus([[obj(.15),obj(.8,.89)],*rows[1:]],times,.32)
        stationary = track_focus([[obj(.5)]]*5,times,.32)
        ok = (track["state"]=="shadow_proposal"
              and track["min_tracked_coverage"]>=.8
              and missing["state"]=="missing_detection"
              and ambiguous["state"]=="ambiguous_identity"
              and stationary["state"]=="no_safe_improvement")
        result["tracking_geometry"] = {"pass":ok,"moving":track,
            "missing":missing,"ambiguous":ambiguous,"stationary":stationary,
            "scope":"synthetic detection sequences, not real video tracking"}
        if not ok:
            raise RuntimeError("Tracking geometry checks failed")
        result["stage"]="window_geometry"
        seq=[[],[],[],[obj(.5)],[obj(.5)],[obj(.5)],[obj(.5)],[],[]]
        window=best_object_window(seq,list(range(9)),8.,3.)
        empty=best_object_window([[]]*9,list(range(9)),8.,3.)
        window_ok=(window["state"]=="shadow_proposal" and window["start"]==3.
                   and window["end"]==6. and empty["state"]=="no_verified_window")
        result["window_geometry"]={"pass":window_ok,"selected":window,"empty":empty}
        if not window_ok:
            raise RuntimeError("Window geometry checks failed")
        result["stage"]="real_video_inference"
        result["real_video"]=real_video_audit()
        if not result["real_video"]["pass"]:
            raise RuntimeError("Expected person detections in at least two real video frames")
        result.update({"pass": True, "stage": "complete"})
    except Exception as exc:
        result.update(error_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        (out / "report.json").write_text(json.dumps(result, indent=2), encoding="utf8")
        print(result, flush=True)

if __name__ == "__main__":
    main()
