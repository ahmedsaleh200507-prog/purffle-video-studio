"""Model loading and inference smoke; not a semantic accuracy benchmark."""
from PIL import Image,ImageDraw
from pathlib import Path
import json,math
from siglip_review import score,MODEL,REVISION
def main():
    red=Image.new("RGB",(224,224),"white")
    blue=red.copy()
    ImageDraw.Draw(red).rectangle((30,30,194,194),fill="red")
    ImageDraw.Draw(blue).rectangle((30,30,194,194),fill="blue")
    rows=score([red,blue],["A red square on a white background.","A blue square on a white background."])
    ok=len(rows)==2 and all(len(r)==2 and all(math.isfinite(v) for v in r) for r in rows)
    result={"model":MODEL,"revision":REVISION,"inference_pass":ok,"color_pair_ranking":bool(ok and rows[0][0]>rows[0][1] and rows[1][1]>rows[1][0]),"scope":"synthetic smoke only; not footage relevance validation"}
    out=Path("siglip-audit");out.mkdir(exist_ok=True)
    (out/"report.json").write_text(json.dumps(result,indent=2),encoding="utf8")
    print(result,flush=True)
    if not ok or not result["color_pair_ranking"]: raise RuntimeError("SigLIP2 smoke failed")
if __name__=="__main__":main()
