"""Live one-small-request-per-model test. Never print keys, bodies or account IDs."""
import json
from pathlib import Path
from cloud_model_router import Router,MODELS,ModelError
def main():
    router=Router()
    rows=[]
    schema={"type":"object","properties":{"en":{"type":"string"},"de":{"type":"string"}},
            "required":["en","de"],"additionalProperties":False}
    messages=[{"role":"system","content":"Return JSON only."},{"role":"user","content":
              "Write the number four in English in en and German in de. Use words, not digits."}]
    for provider,model in MODELS:
        row={"provider":provider,"model":model}
        if not router.keys[provider]:
            row["status"]="missing_key"
        else:
            try:
                data=json.loads(router.request(provider,model,messages=messages,schema=schema,max_tokens=512,temperature=0))
                row["status"]="verified_bilingual_json" if data["en"].strip().casefold()=="four" and data["de"].strip().casefold()=="vier" else "language_test_failed"
            except ModelError as exc:
                row["status"]="unavailable_"+str(exc.status_code)
            except Exception as exc:
                row["status"]="error_"+type(exc).__name__
        rows.append(row)
        print("[MODEL AUDIT]",model,row["status"],flush=True)
    out=Path("cloud-model-audit")
    out.mkdir(exist_ok=True)
    (out/"report.json").write_text(json.dumps(rows,indent=2),encoding="utf8")
    if not any(r["status"]=="verified_bilingual_json" for r in rows):
        raise RuntimeError("No cloud model passed live structured test; local fallback independent")
if __name__=="__main__":main()
