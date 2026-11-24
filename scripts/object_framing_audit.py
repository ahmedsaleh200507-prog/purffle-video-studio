"""Actual model inference on a known example; not a footage accuracy benchmark."""
import io,json
from pathlib import Path
import requests
from PIL import Image
from object_framing import detect,MODEL,REVISION,stable_focus
def main():
    # Public COCO documentation test fixture only, not a new production source.
    r=requests.get("https://images.cocodataset.org/val2017/000000039769.jpg",timeout=30)
    r.raise_for_status()
    if len(r.content)>5*1024*1024: raise ValueError("Fixture too large")
    with Image.open(io.BytesIO(r.content)) as im: frame=im.convert("RGB")
    cats=detect(frame,"cat")
    result={"model":MODEL,"revision":REVISION,"detections":cats,
        "pass":bool(cats),"scope":"real photo inference smoke; not production footage validation"}
    out=Path("object-framing-audit");out.mkdir(exist_ok=True)
    (out/"report.json").write_text(json.dumps(result,indent=2),encoding="utf8")
    print(result,flush=True)
    if not cats: raise RuntimeError("Expected a visible cat in the documented test fixture")
if __name__=="__main__":main()
