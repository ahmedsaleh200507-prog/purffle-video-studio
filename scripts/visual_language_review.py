"""Bounded multi-frame caption observations; never decide footage acceptance.

Reuse pinned engines, release each model after a batch, and retain sampled
frame indices. Captions are evidence, not proof of an action.
"""
import gc
import os
import threading
import time

_LOCK = threading.RLock()
_COUNTS = {"florence": 0, "qwen": 0}
_LIMITS = {"florence": 6, "qwen": 4}
_FAILED = set()

def enabled():
    return os.environ.get("PURFFLE_VLM_SHADOW") == "1"

def _bounded_env(name, default, low, high):
    try:
        return max(low, min(high, int(os.environ.get(name, default))))
    except (TypeError, ValueError):
        return default

def _sample_indices(length, count):
    if not length or count <= 0:
        return []
    middle = length // 2
    if count == 1 or length == 1:
        return [middle]
    if count == 2:
        return sorted({0, length - 1})
    return sorted({0, middle, length - 1})

def _infer_many(key, frames):
    from visual_language_audit import load_engine, caption
    processor, model = load_engine(key)
    try:
        answers = []
        for frame in frames:
            image = frame.copy()
            image.thumbnail((640, 640))
            answers.append(caption(key, processor, model, image))
        return answers
    finally:
        del model, processor
        gc.collect()

def _infer(key, frame):
    return _infer_many(key, [frame])[0]

def observe(frames, subject, query):
    if not enabled():
        return {"state": "disabled"}
    if not frames:
        return {"state": "no_frames"}
    requested = _bounded_env("PURFFLE_VLM_FRAMES", 2, 1, 3)
    result = {"state": "shadow_only", "subject": str(subject)[:200],
              "query": str(query)[:300], "sample_index": len(frames)//2,
              "models": {}, "scope": "sampled frame captions; no acceptance or action verdict"}
    with _LOCK:
        for key in ("florence", "qwen"):
            if key in _FAILED:
                result["models"][key] = {"state": "unavailable"}
                continue
            limit = _bounded_env("PURFFLE_VLM_" + key.upper() + "_BUDGET",
                                 _LIMITS[key], 0, 12)
            remaining = limit - _COUNTS[key]
            indices = _sample_indices(len(frames), min(requested, remaining))
            if not indices:
                result["models"][key] = {"state": "budget_exhausted"}
                continue
            _COUNTS[key] += len(indices)
            t = time.monotonic()
            try:
                if len(indices) == 1:
                    answers = [_infer(key, frames[indices[0]])]
                else:
                    answers = _infer_many(key, [frames[i] for i in indices])
                if len(answers) != len(indices) or any(not str(a or "").strip() for a in answers):
                    raise ValueError("Missing frame caption")
                samples = [{"frame_index": i, "caption": str(a)[:1000]}
                           for i, a in zip(indices, answers)]
                result["models"][key] = {"state": "observed",
                    "caption": samples[0]["caption"], "samples": samples,
                    "sample_indices": indices,
                    "seconds": round(time.monotonic()-t, 2)}
            except Exception as exc:
                _FAILED.add(key)
                result["models"][key] = {"state": "unavailable", "error_type": type(exc).__name__,
                    "error_detail": "see error type"}
        print("[VLM SHADOW]", result, flush=True)
    return result
