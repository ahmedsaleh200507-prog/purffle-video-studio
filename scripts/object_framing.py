"""Open-vocabulary object localization and stable, independently verified crop proposals.

No external inference API. A detection is not proof of an action or identity.
Never reject valid footage solely because this optional model is unavailable.
"""
import os
import math
import statistics
import threading
MODEL="IDEA-Research/grounding-dino-tiny"
REVISION="a2bb814dd30d776dcf7e30523b00659f4f141c71"
_LOCK=threading.RLock()
_ENGINE=None
_FAILED=False

def enabled():
    return os.environ.get("PURFFLE_SMART_CROP")=="1"

def detect(frame,subject):
    global _ENGINE,_FAILED
    with _LOCK:
        if _FAILED: raise RuntimeError("Grounding DINO unavailable")
        try:
            import torch
            from transformers import AutoProcessor,AutoModelForZeroShotObjectDetection
            if _ENGINE is None:
                processor=AutoProcessor.from_pretrained(MODEL,revision=REVISION,trust_remote_code=False)
                model=AutoModelForZeroShotObjectDetection.from_pretrained(MODEL,revision=REVISION,
                    trust_remote_code=False,use_safetensors=True).eval()
                _ENGINE=processor,model
            processor,model=_ENGINE
            query=" ".join(str(subject).casefold().split())[:120].rstrip(".")+"."
            inputs=processor(images=frame,text=query,return_tensors="pt")
            with torch.inference_mode():
                output=model(**inputs)
            result=processor.post_process_grounded_object_detection(output,inputs.input_ids,
                threshold=.35,text_threshold=.25,target_sizes=[frame.size[::-1]])[0]
            w,h=frame.size
            out=[]
            for box,score in zip(result["boxes"].tolist(),result["scores"].tolist()):
                x0,y0,x1,y1=box
                coords=[max(0.,min(1.,v)) for v in (x0/w,y0/h,x1/w,y1/h)]
                if all(math.isfinite(v) for v in coords) and coords[2]>coords[0] and coords[3]>coords[1]:
                    out.append({"box":coords,"score":float(score)})
            return sorted(out,key=lambda b:-b["score"])[:6]
        except Exception:
            _ENGINE=None
            _FAILED=True
            raise

def stable_focus(detections,crop_fraction,default=.5):
    """Find a fixed crop retaining most of the strongest box over sampled moments.

    Never animate the camera based on noisy isolated detections. If there is
    insufficient stable evidence, return no proposal and retain existing crop.
    """
    if not 0<crop_fraction<=1: raise ValueError("Invalid crop fraction")
    boxes=[row[0]["box"] for row in detections if row and row[0]["score"]>=.35]
    if len(boxes)<max(2,(len(detections)+1)//2):
        return {"state":"insufficient_detections","focus_x":default,"detected_frames":len(boxes)}
    half=crop_fraction/2
    def clamp(v): return max(half,min(1-half,v))
    candidates=[clamp(default),clamp(statistics.median((b[0]+b[2])/2 for b in boxes))]
    candidates.extend(clamp((b[0]+b[2])/2) for b in boxes)
    def coverage(f,b):
        return max(0.,min(f+half,b[2])-max(f-half,b[0]))/(b[2]-b[0])
    def rank(f):
        scores=[coverage(f,b) for b in boxes]
        return (sum(x>=.8 for x in scores),statistics.mean(scores),-abs(f-default))
    chosen=max(candidates,key=rank)
    base=rank(clamp(default)); best=rank(chosen)
    # Require clear improvement and coverage of at least two frames.
    proposed=best[0]>=2 and best[1]>=base[1]+.10
    return {"state":"proposed" if proposed else "keep_default",
            "focus_x":round(chosen if proposed else clamp(default),5),
            "detected_frames":len(boxes),"sampled_frames":len(detections),
            "default_box_coverage":round(base[1],4),"proposed_box_coverage":round(best[1],4),
            "model":MODEL,"revision":REVISION,"sampled_boxes":boxes}

def propose(path,seconds,subject,source_width,source_height,output_width,output_height,default=.5):
    if not enabled(): return {"state":"disabled","focus_x":default}
    fraction=min(1.,source_height*output_width/(source_width*output_height))
    if fraction>=.98: return {"state":"no_horizontal_crop","focus_x":default}
    try:
        from media_validation import _frame
        times=(.15,max(.2,seconds*.45),max(.3,min(seconds*.85,seconds-.15)))
        frames=[_frame(path,t,640,preserve_aspect=True) for t in times]
        rows=[detect(frame,subject) for frame in frames]
        return stable_focus(rows,fraction,default)
    except Exception as exc:
        print("[OBJECT FRAMING UNAVAILABLE]",type(exc).__name__,flush=True)
        return {"state":"unavailable","focus_x":default,"error_type":type(exc).__name__}
