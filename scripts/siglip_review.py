"""Pinned independent SigLIP2 image-text ranking. No external inference API.

Experimental until real positive/negative footage evaluation passes.
Do not treat raw logits as calibrated probabilities or prove an event.
"""
import os
import threading
MODEL="google/siglip2-base-patch16-224"
REVISION="02c35f2c035e0ed4a367fb10a892c1fe2a3f364e"
_LOCK=threading.RLock()
_ENGINE=None
_FAILED=False

from visual_score_cache import ExactScoreCache
_SCORE_CACHE=ExactScoreCache()

def score(frames,captions):
    return _SCORE_CACHE.score(frames,captions,_uncached_score)

def _uncached_score(frames,captions):
    global _ENGINE,_FAILED
    with _LOCK:
        if _FAILED:
            raise RuntimeError("SigLIP2 unavailable")
        try:
            import torch
            from transformers import AutoModel,AutoProcessor
            if _ENGINE is None:
                processor=AutoProcessor.from_pretrained(MODEL,revision=REVISION,trust_remote_code=False)
                model=AutoModel.from_pretrained(MODEL,revision=REVISION,trust_remote_code=False,
                                               use_safetensors=True).eval()
                _ENGINE=processor,model
            processor,model=_ENGINE
            inputs=processor(text=captions,images=frames,padding="max_length",
                             max_length=64,truncation=True,return_tensors="pt")
            with torch.inference_mode():
                output=model(**inputs)
            return output.logits_per_image.float().cpu().tolist()
        except Exception:
            _FAILED=True
            _ENGINE=None
            raise

def check(frames,subject,query):
    from video_first_policy import contrast_prompts
    positive=[f"A real documentary photograph showing {subject}.",
              f"A real photograph of {query}."]
    negative=["An empty unrelated background without the requested subject.",
              "A drawing, cartoon or animation.",*contrast_prompts(subject,query)]
    rows=score(frames,positive+negative)
    matches=sum(min(r[:2])>max(r[2:]) for r in rows)
    return {"model":MODEL,"revision":REVISION,"matching_frames":matches,
            "sampled_frames":len(rows),"agrees":matches>=max(1,(len(rows)+1)//2),
            "method":"independent_uncalibrated_logit_ranking"}

def observe(frames,subject,query):
    if os.environ.get("PURFFLE_SIGLIP_REVIEW")!="1":
        return {"state":"disabled"}
    try:
        return {"state":"observed",**check(frames,subject,query)}
    except Exception as exc:
        print("[SIGLIP REVIEW UNAVAILABLE]",type(exc).__name__,flush=True)
        return {"state":"unavailable","error_type":type(exc).__name__}
