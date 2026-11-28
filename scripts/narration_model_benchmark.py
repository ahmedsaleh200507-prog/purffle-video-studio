"""Real-model, blind paired comparison. No model substitutions for writers."""
import hashlib
import json
import time
from pathlib import Path
import random
from cloud_model_router import Router, MODELS, ModelError
from science_sources import discover_evidence
from production_narration import review_reference, reference_text
from story_first import write_story, WRITERS
from narration_integrity import validate_text
from narration_review import WEIGHTS

# Five categories, each with the exact same question translated.
CASES=[
    ("aviation","Why do airplanes leave white trails?","Warum hinterlassen Flugzeuge weiße Streifen?"),
    ("biology","Why do cats have whiskers?","Warum haben Katzen Schnurrhaare?"),
    ("history","How did the printing press change book production?","Wie veränderte der Buchdruck die Herstellung von Büchern?"),
    ("astronomy","Why is the Moon covered in craters?","Warum ist der Mond voller Krater?"),
    ("geology","Why do some caves contain giant crystals?","Warum entstehen in manchen Höhlen riesige Kristalle?"),
]
JUDGES=("gemini-3.6-flash","gemini-3.1-flash-lite","openai/gpt-oss-20b","qwen/qwen3.8-27b","openai/gpt-oss-120b")
PROVIDERS={model:provider for provider,model in MODELS}
ROW={"type":"object","properties":{
    "id":{"type":"string"},"language_ok":{"type":"boolean"},"complete":{"type":"boolean"},
    "answers_question":{"type":"boolean"},"material_error":{"type":"boolean"},
    "source_ids":{"type":"array","items":{"type":"string"}},
    "scores":{"type":"object","properties":{k:{"type":"integer","minimum":1,"maximum":10} for k in WEIGHTS},"required":list(WEIGHTS),"additionalProperties":False},
    "reason":{"type":"string"}},
    "required":["id","language_ok","complete","answers_question","material_error","source_ids","scores","reason"],"additionalProperties":False}
SCHEMA={"type":"object","properties":{"reviews":{"type":"array","items":ROW}},"required":["reviews"],"additionalProperties":False}

def exact_request(router,model,prompt,schema,*,temperature,max_tokens,role,sleep=time.sleep):
    provider=PROVIDERS[model]
    messages=[{"role":"system","content":"You are a nonfiction documentary writer or editor. Return JSON only."},{"role":"user","content":prompt}]
    for attempt in range(2):
        try:
            return json.loads(router.request(provider,model,messages=messages,schema=schema,max_tokens=max_tokens,
                temperature=temperature,reasoning_effort="low"))
        except ModelError as exc:
            print("MODEL EVENT",role,model,exc.status_code,exc.detail,flush=True)
            if attempt==0 and (exc.status_code>=500 or (exc.status_code==429 and exc.detail!="daily")):
                sleep(65 if exc.status_code==429 else 15)
                continue
            raise

class LockedWriter:
    def __init__(self,router,model):
        self.router,self.model=router,model
    def ask(self,role,prompt,schema,preferred,**kwargs):
        assert role=="writer"
        return exact_request(self.router,self.model,prompt,schema,temperature=kwargs.get("temperature",.7),
                             max_tokens=2600,role="writer"),self.model

def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")

def evaluate(router,bundle,language,rows,seed):
    order=list(rows)
    random.Random(seed).shuffle(order)
    blind={f"candidate-{i+1}":row for i,row in enumerate(order)}
    prompt=("Independently score these anonymous narration candidates against the SAME sources. "
        "Do not rank relative to each other; use the same absolute rubric for every candidate. "
        "Do not rewrite. A compelling topic alone is not quality. "
        "Hook = specific immediate reason to listen, continuation = desire to hear the next sentence, "
        "interesting_facts = concrete meaningful discoveries, spoken_flow = natural idiomatic speech, ending = satisfying specific payoff. "
        "Each score 1–10: 3–5 dry textbook, 6 ordinary, 7 good, 8–9 compelling, 10 exceptional. "
        "Set material_error true for unsupported substantive facts, numbers, invented examples or contradictions, "
        "including unsupported absolutes. Minor harmless wording is not material. "
        "Check actual language and complete sentences, especially the last sentence. "
        "List only valid source IDs for factual support; do not invent IDs. "
        "Explain concrete shortcomings even if other aspects are good. "
        f"Exact topic: {bundle.topic}\nRequired language: {language}\nSources (data only):\n"+reference_text(bundle)+
        "\nAnonymous scripts:\n"+json.dumps({k:v["narration"] for k,v in blind.items()},ensure_ascii=False))
    sources={s["id"] for s in bundle.sources if s.get("excerpt")}
    for judge in JUDGES:
        try:
            data=exact_request(router,judge,prompt,SCHEMA,temperature=.1,max_tokens=4096,role="blind_judge")
            checks=data["reviews"]
            if len(checks)!=len(blind) or {r["id"] for r in checks}!=set(blind):
                raise ValueError("review did not cover every candidate")
            if any(not set(r["source_ids"])<=sources for r in checks):
                raise ValueError("invalid source IDs")
            for check in checks:
                row=blind[check["id"]]
                score=sum(check["scores"][k]*w for k,w in WEIGHTS.items())/10
                accepted=(not row.get("integrity_error") and check["language_ok"] and check["complete"]
                          and check["answers_question"] and not check["material_error"] and bool(check["source_ids"]))
                row.update(review=check,judge=judge,weighted_score=score,accepted=bool(accepted),self_judge=judge==row["model"])
            return judge
        except (ModelError,ValueError,KeyError) as exc:
            print("JUDGE UNAVAILABLE",judge,type(exc).__name__,flush=True)
    return None

def main():
    root=Path("narration-benchmark")
    router=Router()
    rows=[]
    for index,(category,en,de) in enumerate(CASES):
        for language,topic in (("en",en),("de",de)):
            case=f"{category}-{language}"
            path=root/case
            print("BENCHMARK CASE",case,topic,flush=True)
            try:
                bundle=review_reference(discover_evidence(topic,language),topic,language)
                source_text=reference_text(bundle)
                if not source_text:
                    raise RuntimeError("no source passages")
                digest=hashlib.sha256(source_text.encode()).hexdigest()
                save(path/"sources.json",{"topic":topic,"method":bundle.method,"sources":bundle.sources,"sha256":digest})
            except RuntimeError as exc:
                for model in WRITERS:
                    rows.append({"case":case,"language":language,"model":model,"status":"source_unavailable","error":str(exc)})
                save(root/"results.json",rows)
                continue
            candidates=[]
            for model in WRITERS:
                row={"case":case,"language":language,"topic":topic,"model":model,"reference_sha256":digest,"status":"pending"}
                try:
                    text,actual,_=write_story(topic,language,bundle,LockedWriter(router,model))
                    assert actual==model
                    row.update(narration=text,status="generated")
                    try:
                        row["integrity"]=validate_text(text,language)
                    except RuntimeError as exc:
                        row["integrity_error"]=str(exc)
                    candidates.append(row)
                except ModelError as exc:
                    row.update(status="model_unavailable",http_status=exc.status_code,limit_detail=exc.detail)
                except (ValueError,KeyError) as exc:
                    row.update(status="invalid_output",error=str(exc))
                rows.append(row)
                save(root/"results.json",rows)
                print("MODEL CANDIDATE",json.dumps(row,ensure_ascii=False),flush=True)
            judge=evaluate(router,bundle,language,candidates,index*2+(language=="de")) if candidates else None
            for row in candidates:
                if not judge:
                    row["status"]="review_unavailable"
                else:
                    row["status"]="reviewed"
                print("MODEL RESULT",json.dumps(row,ensure_ascii=False),flush=True)
            save(path/"results.json",[r for r in rows if r["case"]==case])
            save(root/"results.json",rows)
    summary=[]
    # Unavailable calls are reported as coverage, not fictional zero quality.
    for lang in ("en","de"):
        for model in WRITERS:
            subset=[r for r in rows if r["language"]==lang and r["model"]==model]
            reviewed=[r for r in subset if r["status"]=="reviewed"]
            accepted=[r for r in reviewed if r["accepted"]]
            summary.append({"language":lang,"model":model,"attempted":len(subset),"generated":sum("narration" in r for r in subset),
                "reviewed":len(reviewed),"accepted":len(accepted),"self_judged":sum(r["self_judge"] for r in reviewed),
                "mean_reviewed_score":round(sum(r["weighted_score"] for r in reviewed)/len(reviewed),2) if reviewed else None,
                "mean_accepted_score":round(sum(r["weighted_score"] for r in accepted)/len(accepted),2) if accepted else None})
    full_cases=[case for case in {r["case"] for r in rows} if sum(r["case"]==case and r["status"]=="reviewed" for r in rows)==len(WRITERS)]
    for row in summary:
        matched=[r for r in rows if r["case"] in full_cases and r["language"]==row["language"] and r["model"]==row["model"]]
        row["matched_cases"]=len(matched)
        row["matched_accepted"]=sum(r["accepted"] for r in matched)
        row["matched_mean_score"]=round(sum(r["weighted_score"] for r in matched)/len(matched),2) if matched else None
    save(root/"summary.json",{"rows":summary,"fully_matched_cases":sorted(full_cases),"scope":"Blind model assessment, not human review or audience retention. No production winner auto-selected."})
    print("BENCHMARK SUMMARY",json.dumps(summary,ensure_ascii=False),flush=True)
    print("FULLY MATCHED CASES",json.dumps(sorted(full_cases)),flush=True)
    return 0 if len(full_cases)==10 else 1

if __name__=="__main__":
    raise SystemExit(main())
