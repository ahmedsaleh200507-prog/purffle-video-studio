"""Independent CPU caption smoke for two local vision-language models.

Not a production gate, action recognition test, or representative benchmark.
No paid inference, remote executable model code, or production changes.
"""
import argparse
import io
import json
import re
import time
from pathlib import Path

import requests
import torch
from PIL import Image
from transformers import AutoProcessor

MODELS = {
    "florence": ("florence-community/Florence-2-base-ft", "0b03b6f15a4a211370fb204aee4e7dd48887ea37"),
    "qwen": ("Qwen/Qwen3-VL-2B-Instruct", "89644892e4d85e24eaac8bacfd4f463576704203"),
}
FIXTURES = [
    ("cats", "https://huggingface.co/datasets/huggingface/documentation-images/resolve/main/coco_sample.png",
     r"\b(?:cats?|kittens?|felines?)\b", r"\b(?:cars?|automobiles?|vehicles?)\b"),
    ("car", "https://huggingface.co/datasets/huggingface/documentation-images/resolve/main/transformers/tasks/car.jpg",
     r"\b(?:cars?|automobiles?|vehicles?)\b", r"\b(?:cats?|kittens?|felines?)\b"),
]

def load_image(url):
    with requests.get(url, stream=True, timeout=(10, 40)) as response:
        response.raise_for_status()
        data = bytearray()
        for chunk in response.iter_content(65536):
            data.extend(chunk)
            if len(data) > 8 * 1024 * 1024:
                raise ValueError("Fixture exceeds byte limit")
    with Image.open(io.BytesIO(data)) as im:
        image = im.convert("RGB")
        image.thumbnail((640, 640))
        return image

def load_engine(key):
    name, revision = MODELS[key]
    options = {"revision": revision, "trust_remote_code": False}
    processor = AutoProcessor.from_pretrained(name, **options)
    if key == "florence":
        from transformers import Florence2ForConditionalGeneration
        model = Florence2ForConditionalGeneration.from_pretrained(
            name, **options, use_safetensors=True, dtype=torch.float32)
    else:
        from transformers import Qwen3VLForConditionalGeneration
        model = Qwen3VLForConditionalGeneration.from_pretrained(
            name, **options, use_safetensors=True, dtype=torch.bfloat16,
            attn_implementation="sdpa")
    return processor, model.eval()

def caption(key, processor, model, image):
    with torch.inference_mode():
        if key == "florence":
            task = "<DETAILED_CAPTION>"
            inputs = processor(text=task, images=image, return_tensors="pt")
            ids = model.generate(**inputs, max_new_tokens=80, num_beams=1, do_sample=False)
            raw = processor.batch_decode(ids, skip_special_tokens=False)[0]
            parsed = processor.post_process_generation(raw, task=task, image_size=image.size)
            return str(parsed[task]).strip()
        messages = [{"role": "user", "content": [
            {"type": "image"},
            {"type": "text", "text": "Describe the main visible objects in this image in one or two short factual sentences. Do not guess."},
        ]}]
        prompt = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = processor(text=[prompt], images=[image], return_tensors="pt")
        ids = model.generate(**inputs, max_new_tokens=80, do_sample=False)
        new_ids = ids[:, inputs.input_ids.shape[1]:]
        return processor.batch_decode(new_ids, skip_special_tokens=True)[0].strip()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, choices=MODELS)
    key = parser.parse_args().model
    name, revision = MODELS[key]
    out = Path("visual-language-audit")
    out.mkdir(exist_ok=True)
    report = {"model": name, "revision": revision, "device": "cpu", "pass": False,
              "scope": "two known still images; lexical smoke only; no video or action accuracy",
              "cases": [], "stage": "load"}
    try:
        torch.set_num_threads(2)
        t = time.monotonic()
        processor, model = load_engine(key)
        report["load_seconds"] = round(time.monotonic() - t, 2)
        report["stage"] = "inference"
        for label, url, positive, negative in FIXTURES:
            image = load_image(url)
            t = time.monotonic()
            answer = caption(key, processor, model, image)
            seconds = round(time.monotonic() - t, 2)
            expected = bool(re.search(positive, answer, re.I))
            unexpected = bool(re.search(negative, answer, re.I))
            report["cases"].append({"fixture": label, "url": url, "caption": answer,
                "seconds": seconds, "expected_word": expected, "unexpected_word": unexpected,
                "pass": bool(answer and expected and not unexpected)})
        report["pass"] = all(row["pass"] for row in report["cases"]) and len(report["cases"]) == len(FIXTURES)
        report["stage"] = "complete"
        if not report["pass"]:
            raise RuntimeError("Caption smoke failed; inspect generated descriptions")
    except Exception as exc:
        report.update(error_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        (out / (key + ".json")).write_text(json.dumps(report, indent=2), encoding="utf8")
        print(json.dumps(report, ensure_ascii=False), flush=True)

if __name__ == "__main__":
    main()
