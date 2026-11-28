"""Independent CPU video-model audition. No production imports of this module."""
import argparse
import json
import re
import subprocess
import tempfile
import time
from pathlib import Path

MODELS={
    "qwen4b":("Qwen/Qwen3-VL-4B-Instruct","264f17f202db5796c7039d94d0c024668a6ac27e"),
    "smolvlm":("HuggingFaceTB/SmolVLM2-2.2B-Instruct","482adb537c021c86670beed01cd58990d01e72e4"),
    "qwen2b":("Qwen/Qwen3-VL-2B-Instruct","89644892e4d85e24eaac8bacfd4f463576704203"),
}
QUESTIONS=("Are people visible?", "Is a person riding a bicycle?",
           "Do any people visibly change position across the video frames?")
EXPECTED={"moving":(True,False,True),"frozen":(True,False,False)}
def prompt():
    return ("Examine the actual ordered video frames, not just one frame. "
            "Do not guess from the scene context. Answer each question independently. "
            "Use null if uncertain. Return only JSON with keys first, second, third, "
            "each true, false, or null. first: "+QUESTIONS[0]+" second: "+QUESTIONS[1]+" third: "+QUESTIONS[2])
def score(raw,case):
    raw=raw.strip()
    fenced=re.fullmatch(r"```(?:json)?\s*([\s\S]*?)\s*```",raw,re.I)
    if fenced:
        raw=fenced.group(1)
    row=json.loads(raw)
    if not isinstance(row,dict) or set(row)!={"first","second","third"} or any(type(v) is not bool and v is not None for v in row.values()):
        raise ValueError("invalid verdict format")
    verdict=[row[k] for k in ("first","second","third")]
    expected=EXPECTED[case]
    return {"verdict":verdict,"expected":list(expected),
            "correct":sum(v is e for v,e in zip(verdict,expected)),
            "false_positive":sum(v is True and e is False for v,e in zip(verdict,expected)),
            "abstentions":sum(v is None for v in verdict)}
def prepare(directory):
    from video_contrast_audit import fixture
    source=directory/"people.avi"
    fixture(source)
    # The moving and frozen controls start from the same source time.
    # 4 seconds at 2fps; native video input, not a caption of a still frame.
    moving=directory/"moving.mp4"
    frozen=directory/"frozen.mp4"
    still=directory/"still.png"
    def run(args):
        subprocess.run(["ffmpeg","-nostdin","-hide_banner","-loglevel","error","-y",*args],
                       check=True,timeout=45)
    run(["-ss","1","-i",str(source),"-t","4","-vf","fps=2,scale=448:-2","-an",
         "-c:v","libx264","-pix_fmt","yuv420p",str(moving)])
    run(["-i",str(moving),"-frames:v","1",str(still)])
    run(["-loop","1","-framerate","2","-i",str(still),"-t","4","-an",
         "-c:v","libx264","-pix_fmt","yuv420p",str(frozen)])
    return {"moving":moving,"frozen":frozen}
def local_engine(key):
    import torch
    from transformers import AutoProcessor, AutoModelForImageTextToText
    name,revision=MODELS[key]
    opts={"revision":revision,"trust_remote_code":False}
    processor=AutoProcessor.from_pretrained(name,**opts)
    model=AutoModelForImageTextToText.from_pretrained(name,**opts,
                use_safetensors=True,dtype=torch.bfloat16,attn_implementation="sdpa",
                low_cpu_mem_usage=True).eval()
    return processor,model
def infer(engine,path):
    import torch
    processor,model=engine
    messages=[{"role":"user","content":[{"type":"video","path":str(path)},
              {"type":"text","text":prompt()}]}]
    inputs=processor.apply_chat_template(messages,add_generation_prompt=True,
              tokenize=True,return_dict=True,return_tensors="pt",num_frames=8,
              video_load_backend="decord")
    if not any(k in inputs for k in ("pixel_values_videos","pixel_values","video_grid_thw")):
        raise ValueError("video pixels not present in processed input")
    inputs=inputs.to(model.device,dtype=torch.bfloat16)
    with torch.inference_mode():
        ids=model.generate(**inputs,max_new_tokens=96,do_sample=False)
    return processor.batch_decode(ids[:,inputs["input_ids"].shape[1]:],
                                   skip_special_tokens=True)[0].strip()
def main(key):
    import torch
    torch.set_num_threads(2)
    out=Path("temporal-vision-pilot")
    out.mkdir(exist_ok=True)
    report={"model":MODELS[key][0],"revision":MODELS[key][1],
            "scope":"One real clip and its frozen control; not general video accuracy.",
            "cases":{},"planned_questions":6,"stage":"prepare"}
    try:
        with tempfile.TemporaryDirectory() as tmp:
            paths=prepare(Path(tmp))
            report["stage"]="load"
            start=time.monotonic()
            engine=local_engine(key)
            report["load_seconds"]=round(time.monotonic()-start,2)
            report["stage"]="inference"
            for case,path in paths.items():
                start=time.monotonic()
                try:
                    raw=infer(engine,path)
                    row={"status":"evaluated",**score(raw,case),"answer":raw[:1000]}
                except Exception as exc:
                    row={"status":"error","error_type":type(exc).__name__,"error":str(exc)[:300]}
                row["seconds"]=round(time.monotonic()-start,2)
                report["cases"][case]=row
                print("TEMPORAL VISION CASE",key,case,json.dumps(row),flush=True)
            report["stage"]="complete"
    except Exception as exc:
        report["error_type"]=type(exc).__name__
        report["error"]=str(exc)[:300]
    finally:
        rows=list(report["cases"].values())
        report["evaluated_questions"]=3*sum(r["status"]=="evaluated" for r in rows)
        report["correct"]=sum(r.get("correct",0) for r in rows)
        report["false_positives"]=sum(r.get("false_positive",0) for r in rows)
        report["pass"]=report["correct"]==6 and report["evaluated_questions"]==6
        (out/(key+".json")).write_text(json.dumps(report,indent=2))
        print("TEMPORAL VISION SUMMARY",json.dumps(report),flush=True)
    return 0 if report["pass"] else 1
if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--model",required=True,choices=MODELS)
    raise SystemExit(main(parser.parse_args().model))
