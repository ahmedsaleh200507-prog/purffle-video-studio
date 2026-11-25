"""Actual model inference on a known example; not a footage accuracy benchmark."""
import io
import json
from pathlib import Path
import requests
from PIL import Image
from object_framing import detect, MODEL, REVISION, track_focus

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
        result.update({"pass": True, "stage": "complete"})
    except Exception as exc:
        result.update(error_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        (out / "report.json").write_text(json.dumps(result, indent=2), encoding="utf8")
        print(result, flush=True)

if __name__ == "__main__":
    main()
