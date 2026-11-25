"""Bounded optional caption observations; never decide footage acceptance.

Reuse the pinned audited engines. Limit CPU inference per worker process and
release models after use. A caption is evidence, not proof of an action.
"""
import gc
import os
import threading
import time

_LOCK = threading.RLock()
_COUNTS = {"florence": 0, "qwen": 0}
_LIMITS = {"florence": 2, "qwen": 1}
_FAILED = set()

def enabled():
    return os.environ.get("PURFFLE_VLM_SHADOW") == "1"

def _infer(key, frame):
    from visual_language_audit import load_engine, caption
    processor, model = load_engine(key)
    try:
        image = frame.copy()
        image.thumbnail((640, 640))
        return caption(key, processor, model, image)
    finally:
        del model, processor
        gc.collect()

def observe(frames, subject, query):
    if not enabled():
        return {"state": "disabled"}
    if not frames:
        return {"state": "no_frames"}
    result = {"state": "shadow_only", "subject": str(subject)[:200],
              "query": str(query)[:300], "sample_index": len(frames)//2,
              "models": {}, "scope": "single sampled frame captions; no acceptance or action verdict"}
    with _LOCK:
        for key in ("florence", "qwen"):
            if key in _FAILED:
                result["models"][key] = {"state": "unavailable"}
                continue
            if _COUNTS[key] >= _LIMITS[key]:
                result["models"][key] = {"state": "budget_exhausted"}
                continue
            _COUNTS[key] += 1
            t = time.monotonic()
            try:
                answer = _infer(key, frames[result["sample_index"]])
                result["models"][key] = {"state": "observed", "caption": str(answer)[:1000],
                    "seconds": round(time.monotonic()-t, 2)}
            except Exception as exc:
                _FAILED.add(key)
                result["models"][key] = {"state": "unavailable", "error_type": type(exc).__name__}
        print("[VLM SHADOW]", result, flush=True)
    return result
