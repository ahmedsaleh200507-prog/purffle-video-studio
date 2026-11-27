"""User-approved, pinned Kokoro George. CPU only, no alternate narrator.

Kokoro duration tokens are predictions. Actual WAV ASR independently checks
the spoken text and timing; never describe the result as native Piper samples.
"""
from functools import lru_cache
import hashlib
import math
import os
from pathlib import Path
import re
import wave

REPO="hexgrad/Kokoro-82M"
REVISION="f3ff3571791e39611d31c381e3a41a3af07b4987"
MODEL_HASH="496dba118d1a58f5f3db2efc88dbdc216e0483fc89fe6e47ee1f2c53f18ad1e4"
VOICE_HASH="f1bc812213dc59774769e5c80004b13eeb79bd78130b11b2d7f934542dab811b"
VOICE="bm_george"
ALIGNMENT="kokoro_duration_tokens_crosschecked_against_actual_wav_asr"
VERSION="george_v1"
BASE=f"https://huggingface.co/{REPO}/resolve/{REVISION}/"

def provenance():
    return {"engine":"kokoro","model":VOICE,"model_revision":REVISION,
            "model_url":BASE+"kokoro-v1_0.pth","model_sha256":MODEL_HASH,
            "voice_sha256":VOICE_HASH,"voice_url":BASE+"voices/"+VOICE+".pt",
            "license":{"id":"Apache-2.0","url":f"https://huggingface.co/{REPO}/blob/{REVISION}/README.md"},
            "alignment":ALIGNMENT,"voice_flow_version":VERSION,"speed":1.0,
            "software_version":"kokoro==0.9.4"}

def verify_provenance(proof):
    expected=provenance()
    if not isinstance(proof,dict) or any(proof.get(k)!=v for k,v in expected.items()):
        raise RuntimeError("George voice identity or pinned provenance invalid")
    review=proof.get("actual_wav_alignment",{})
    if (review.get("verified") is not True or review.get("asr_model") not in ("base.en","small.en","mixed")
            or int(review.get("words",0))<=0 or not 0<=float(review.get("max_boundary_delta",float("inf")))<=.85):
        raise RuntimeError("George independent actual-audio alignment missing")

def _sha(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f,"sha256").hexdigest()

@lru_cache(maxsize=1)
def _load():
    import torch
    from kokoro import KModel,KPipeline
    from huggingface_hub import hf_hub_download
    def fetch(name):
        return Path(hf_hub_download(repo_id=REPO,filename=name,revision=REVISION))
    weights=fetch("kokoro-v1_0.pth")
    pack=fetch("voices/"+VOICE+".pt")
    if _sha(weights)!=MODEL_HASH or _sha(pack)!=VOICE_HASH:
        raise RuntimeError("George model or voice fingerprint mismatch")
    torch.set_num_threads(2)
    model=KModel(repo_id=REPO,config=str(fetch("config.json")),model=str(weights)).to("cpu").eval()
    return KPipeline(lang_code="b",repo_id=REPO,model=model,device="cpu"),torch.load(str(pack),weights_only=True,map_location="cpu")

def _atoms(text):
    from approved_reference_voice import _tokens
    return _tokens(text)

def _map_tokens(original,rows,duration):
    """Match every original word to actual model/ASR lexical tokens.
    Hyphenated words may occupy several rows; never interpolate time.
    """
    expected=[_atoms(t) for t in original]
    groups=[(_atoms(t),float(a),float(b)) for t,a,b in rows if _atoms(t)]
    if any(not e for e in expected) or [x for e in expected for x in e]!=[x for g,_,_ in groups for x in g]:
        raise RuntimeError("George transcript token mismatch")
    out=[]
    cursor=0
    previous=0.
    for token,atoms in zip(original,expected):
        found=[]
        begin=cursor
        while len(found)<len(atoms) and cursor<len(groups):
            found.extend(groups[cursor][0]); cursor+=1
        if found!=atoms:
            raise RuntimeError("George ambiguous lexical word boundary")
        a,b=groups[begin][1],groups[cursor-1][2]
        if not all(math.isfinite(v) for v in (a,b)) or a<previous-.035 or b<=a or a<0 or b>duration+.025:
            raise RuntimeError("George invalid word interval")
        out.append((token,max(previous,a),min(duration,b)))
        if out[-1][2]<=out[-1][1]:
            raise RuntimeError("George zero length word")
        previous=out[-1][2]
    return out

@lru_cache(maxsize=2)
def _asr(model):
    from faster_whisper import WhisperModel
    return WhisperModel(model,device="cpu",compute_type="int8",cpu_threads=2,download_root=os.getenv("PURFFLE_WHISPER_CACHE",".cache/whisper"))

def _verify_wav(text,path,original,predicted,duration):
    from approved_reference_voice import check_real_word_timing
    error=None
    for model in ("base.en","small.en"):
        try:
            raw=check_real_word_timing(text,path,asr_loader=lambda:_asr(model))
            aligned=_map_tokens(original,raw,duration)
            deltas=[max(abs(a[1]-b[1]),abs(a[2]-b[2])) for a,b in zip(aligned,predicted)]
            maximum=max(deltas,default=float("inf"))
            if maximum>.85 or sorted(deltas)[len(deltas)//2]>.30:
                raise RuntimeError("George model/ASR timing disagreement")
            # Keep duration-token timings, which preserve the approved voice's
            # exact lexical boundaries, but only after the independent check.
            return model,maximum
        except RuntimeError as exc:
            error=exc
    raise RuntimeError("George actual-audio verification failed: "+str(error))

def synthesize(text,out,settings):
    if settings.language!="en":
        raise RuntimeError("George is English-only")
    import numpy as np
    from purffle_shorts.timing import Word,tokenize
    from purffle_shorts.tts import Speech
    text=" ".join(str(text).split())
    original=tokenize(text,"en")
    if not 2<=len(original)<=400 or len(text)>6000:
        raise RuntimeError("George narration outside word/character limits")
    pipeline,embedding=_load()
    out=Path(out); out.mkdir(parents=True,exist_ok=True)
    target=out/"voice-george.wav"
    temp=out/"voice-george.wav.part"
    target.unlink(missing_ok=True)
    parts=[]; words=[]; offset=0.; cursor=0; models=set(); max_delta=0.
    try:
        for i,result in enumerate(pipeline(text,voice=embedding,speed=1.0)):
            gs,ps,audio=result
            if i>=16 or audio is None or len(ps)>510:
                raise RuntimeError("George missing or oversized inference chunk")
            signal=audio.detach().cpu().numpy().reshape(-1)
            if not len(signal) or not np.isfinite(signal).all() or np.max(np.abs(signal))<1e-5:
                raise RuntimeError("George invalid audio")
            duration=len(signal)/24000
            tokens=tokenize(gs,"en")
            n=len(tokens)
            if not n or tokens!=original[cursor:cursor+n]:
                raise RuntimeError("George inference changed original narration")
            rows=[]
            for token in (getattr(result,"tokens",None) or []):
                if _atoms(token.text):
                    if token.start_ts is None or token.end_ts is None:
                        raise RuntimeError("George missing duration token")
                    rows.append((token.text,token.start_ts,token.end_ts))
            predicted=_map_tokens(tokens,rows,duration)
            part=out/f"verify-george-{i}.wav"
            def write(path,samples):
                with wave.open(str(path),"wb") as wav:
                    wav.setparams((1,2,24000,0,"NONE","not compressed"))
                    wav.writeframes((np.clip(samples,-1,1)*32767).astype(np.int16).tobytes())
            try:
                write(part,signal*.92/float(np.max(np.abs(signal))))
                model,delta=_verify_wav(gs,part,tokens,predicted,duration)
            finally:
                part.unlink(missing_ok=True)
            models.add(model); max_delta=max(max_delta,delta)
            words.extend(Word(t,a+offset,b+offset) for t,a,b in predicted)
            parts.append(signal); offset+=duration; cursor+=n
            if offset>180: raise RuntimeError("George narration duration budget exceeded")
        if cursor!=len(original) or [w.text for w in words]!=original:
            raise RuntimeError("George incomplete spoken script")
        signal=np.concatenate(parts)
        write(temp,signal*.92/float(np.max(np.abs(signal))))
        temp.replace(target)
    finally:
        temp.unlink(missing_ok=True)
    proof=provenance()
    proof.update(actual_wav_alignment={"verified":True,"words":len(words),"asr_model":next(iter(models)) if len(models)==1 else "mixed","max_boundary_delta":round(max_delta,4)},
                 sample_rate=24000,audio_samples=len(signal),word_count=len(words),timing="aligned")
    verify_provenance(proof)
    speech=Speech(target,words,len(signal)/24000,"kokoro",VOICE,"aligned")
    speech.provenance=proof
    print(f"[GEORGE] words={len(words)} seconds={speech.duration:.3f} ASR={proof['actual_wav_alignment']}",flush=True)
    return speech
