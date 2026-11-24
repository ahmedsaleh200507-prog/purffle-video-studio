"""Lazy CPU-only Qwen fallback. No API keys, remote inference or model code execution."""
import atexit
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import tarfile
import threading
import time
from types import SimpleNamespace

MODEL="Qwen3-4B-Instruct-2507-Q4_K_M"
MODEL_URL="https://huggingface.co/bartowski/Qwen_Qwen3-4B-Instruct-2507-GGUF/resolve/d3037fec123e6fcf1b894f42ff01bd83d4622955/Qwen_Qwen3-4B-Instruct-2507-Q4_K_M.gguf"
MODEL_SHA="2fde00ce69dd4899c70d020845e2638353015bba0fdf161b3eb965f2bca4464e"
QUALITY_MODEL="Qwen3-8B-Q4_K_M"
QUALITY_URL="https://huggingface.co/Qwen/Qwen3-8B-GGUF/resolve/6a569868d07d3bd59e8b97fb001bf8c0b254bb20/Qwen3-8B-Q4_K_M.gguf"
QUALITY_SHA="d98cdcbd03e17ce47681435b5150e34c1417f50b5c0019dd560e4882c5745785"
MODELS={"fast":(MODEL,MODEL_URL,MODEL_SHA,3*1024**3),
        "quality":(QUALITY_MODEL,QUALITY_URL,QUALITY_SHA,6*1024**3)}
ENGINE_URL="https://github.com/ggml-org/llama.cpp/releases/download/b12644/llama-b12644-bin-ubuntu-x64.tar.gz"
ENGINE_SHA="7cff30bdd348bd2cf1b999e9323c97491d77dab4f5ce129629f590d75f9e6756"

def enabled(env=None):
    return (os.environ if env is None else env).get("PURFFLE_LOCAL_LLM","0")=="1"

def sha256(path):
    h=hashlib.sha256()
    with open(path,"rb") as file:
        for block in iter(lambda:file.read(1024*1024),b""):
            h.update(block)
    return h.hexdigest()

def download(url,path,expected,max_bytes):
    import requests
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.is_file() and sha256(path)==expected:
        return path
    tmp=path.with_suffix(path.suffix+".part")
    try:
        started=time.monotonic()
        size=0
        with requests.Session() as session:
            session.trust_env=False
            with session.get(url,stream=True,timeout=(15,60)) as response:
                response.raise_for_status()
                with tmp.open("wb") as out:
                    for block in response.iter_content(1024*1024):
                        size+=len(block)
                        if size>max_bytes or time.monotonic()-started>900:
                            raise RuntimeError("Local model download exceeded budget")
                        out.write(block)
        if sha256(tmp)!=expected:
            raise RuntimeError("Local model/runtime checksum mismatch")
        tmp.replace(path)
        return path
    finally:
        tmp.unlink(missing_ok=True)

class LocalQwen:
    def __init__(self,tier="fast"):
        self.tier=tier
        self.model,self.model_url,self.model_sha,self.max_bytes=MODELS[tier]
        self.lock=threading.RLock()
        self.process=None
        self.port=None
        self.failed=False
        self.log=None
        self.root=Path(os.getenv("PURFFLE_LOCAL_LLM_CACHE",".cache/local-llm")).resolve()
        atexit.register(self.close)
    def close(self):
        with self.lock:
            if self.process:
                self.process.terminate()
                try: self.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=5)
                self.process=None
            if self.log:
                self.log.close()
                self.log=None
    def start(self):
        import requests
        if self.process and self.process.poll() is None:
            return
        if self.failed:
            raise RuntimeError("Local Qwen unavailable earlier in this job")
        try:
            if os.uname().sysname!="Linux" or os.uname().machine not in ("x86_64","amd64"):
                raise RuntimeError("Local model runtime requires Linux x64")
            self.root.mkdir(parents=True,exist_ok=True)
            archive=download(ENGINE_URL,self.root/"llama-b12644.tar.gz",ENGINE_SHA,350*1024**2)
            model=download(self.model_url,self.root/(self.model+".gguf"),self.model_sha,self.max_bytes)
            # Always extract from the verified release; never run an unverified
            # executable restored from a cache.
            runtime=self.root/"runtime"
            import shutil
            shutil.rmtree(runtime,ignore_errors=True)
            runtime.mkdir(exist_ok=True)
            with tarfile.open(archive,"r:gz") as tar:
                tar.extractall(runtime,filter="data")
            binary=next((p for p in runtime.rglob("llama-server") if p.is_file()),None)
            if binary is None:
                raise RuntimeError("llama-server missing from official archive")
            with socket.socket() as sock:
                sock.bind(("127.0.0.1",0))
                self.port=sock.getsockname()[1]
            env={**os.environ,"LD_LIBRARY_PATH":str(binary.parent)}
            self.log=(self.root/("server-"+self.tier+".log")).open("w",encoding="utf8")
            threads=max(1,min(4,os.cpu_count() or 1))
            self.process=subprocess.Popen([str(binary),"-m",str(model),"--host","127.0.0.1",
                "--port",str(self.port),"--alias",self.model,"-ngl","0","-c","8192","-t",str(threads),
                "-np","1","--no-webui"],stdout=self.log,stderr=subprocess.STDOUT,env=env)
            end=time.monotonic()+180
            with requests.Session() as session:
                session.trust_env=False
                while time.monotonic()<end:
                    if self.process.poll() is not None:
                        raise RuntimeError("Local Qwen runtime exited during initialization")
                    try:
                        if session.get(f"http://127.0.0.1:{self.port}/health",timeout=3).status_code==200:
                            print("[LOCAL LLM]",self.model,"ready on CPU; model SHA256 verified",flush=True)
                            return
                    except requests.RequestException:
                        pass
                    time.sleep(2)
            raise RuntimeError("Local Qwen startup timeout")
        except Exception:
            self.failed=True
            self.close()
            raise
    def complete(self,messages,*,schema=None,max_tokens=3000,temperature=.2):
        import requests
        with self.lock:
            self.start()
            messages=[dict(m) for m in messages]
            if self.tier=="quality":
                # Qwen3-8B supports the documented soft /no_think switch.
                # Avoid hidden reasoning consuming the CPU/token budget.
                for m in reversed(messages):
                    if m.get("role")=="user":
                        m["content"]=str(m["content"])+"\n/no_think"
                        break
            payload={"model":self.model,"messages":messages,"temperature":max(0.,min(.5,float(temperature))),
                     "max_tokens":min(4500,max(64,int(max_tokens))),"stream":False}
            if self.tier=="quality":
                payload["chat_template_kwargs"]={"enable_thinking":False}
            if schema:
                payload["response_format"]={"type":"json_schema","json_schema":{"name":"purffle","schema":schema,"strict":True}}
            else:
                payload["response_format"]={"type":"json_object"}
            try:
                with requests.Session() as session:
                    session.trust_env=False
                    response=session.post(f"http://127.0.0.1:{self.port}/v1/chat/completions",json=payload,timeout=(5,600))
                    response.raise_for_status()
                    choice=response.json()["choices"][0]
                content=choice["message"]["content"]
                if choice.get("finish_reason")!="stop" or not isinstance(json.loads(content),dict):
                    raise RuntimeError("Local model returned incomplete/nonobject JSON")
                print("[LOCAL LLM]",self.model,"JSON candidate generated; normal validators still required",flush=True)
                return content
            except Exception as exc:
                # No prompt, source excerpts, model output or API secrets in error reports.
                raise RuntimeError("Local Qwen JSON generation failed: "+type(exc).__name__) from None

_INSTANCE=None
_ROUTER_LOCK=threading.RLock()
_FAILED=set()
def instance(tier="fast"):
    global _INSTANCE
    with _ROUTER_LOCK:
        if _INSTANCE is not None and _INSTANCE.tier!=tier:
            _INSTANCE.close()
            _INSTANCE=None
        if _INSTANCE is None:
            _INSTANCE=LocalQwen(tier)
        return _INSTANCE

def complete_adaptive(messages,*,schema=None,max_tokens=3000,temperature=.2,prefer="quality"):
    """One loaded model at a time. Switch only for infrastructure or invalid JSON.
    Substantive negative scientific reviews are returned as-is, never voted away.
    """
    global _INSTANCE
    with _ROUTER_LOCK:
        quality_enabled=os.getenv("PURFFLE_LOCAL_QUALITY","0")=="1"
        order=["quality","fast"] if quality_enabled and prefer=="quality" else ["fast","quality"] if quality_enabled else ["fast"]
        if quality_enabled and _INSTANCE is not None and _INSTANCE.tier=="quality":
            # Keep the larger model warm after escalation rather than swap
            # between generation and review on every chapter.
            order=["quality","fast"]
        for tier in order:
            if tier in _FAILED:
                continue
            try:
                return instance(tier).complete(messages,schema=schema,max_tokens=max_tokens,temperature=temperature)
            except Exception as exc:
                print("[LOCAL ROUTER]",tier,"failed",type(exc).__name__,flush=True)
                if _INSTANCE is not None and _INSTANCE.failed:
                    _FAILED.add(tier)
                if _INSTANCE is not None:
                    _INSTANCE.close()
                    _INSTANCE=None
        raise RuntimeError("All permitted local models unavailable")

def local_completion(**kwargs):
    fmt=kwargs.get("response_format") or {}
    schema=(fmt.get("json_schema") or {}).get("schema")
    content=complete_adaptive(kwargs["messages"],schema=schema,
        max_tokens=kwargs.get("max_tokens",3000),temperature=kwargs.get("temperature",.2),prefer="quality")
    return SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop",message=SimpleNamespace(content=content))])

def install_short_provider(upstream):
    if not enabled() or "purffle-local" in upstream.PRESETS:
        return
    original=upstream.build_provider
    upstream.PRESETS["purffle-local"]=upstream.Preset("purffle-local","Qwen CPU adaptive",
        "http://127.0.0.1",(),QUALITY_MODEL,local=True,schema_mode=True)
    class Provider(upstream.Provider):
        name="purffle-local"
        model=QUALITY_MODEL
        def complete(self,system,user,*,schema=None,temperature=.2,max_tokens=4000):
            return complete_adaptive([{"role":"system","content":system},{"role":"user","content":user}],
                schema=schema,max_tokens=max_tokens,temperature=temperature,prefer="quality")
    def build(name,settings,model=""):
        return Provider() if name=="purffle-local" else original(name,settings,model)
    upstream.build_provider=build

if __name__=="__main__":
    # Real CPU inference smoke check; independent of paid APIs.
    tier=os.getenv("PURFFLE_TEST_MODEL","fast")
    schema={"type":"object","properties":{"answer":{"type":"string"}},"required":["answer"],"additionalProperties":False}
    for lang,prompt,expected in (("en","Reply in English with only the answer to 2+2 in words.","four"),
                                 ("de","Antworte ausschließlich auf Deutsch. Wie viel ist zwei plus zwei? Schreibe die Zahl als deutsches Wort, keine Ziffer.","vier")):
        result=json.loads(instance(tier).complete([{"role":"system","content":"Return JSON with answer."},
                    {"role":"user","content":prompt}],schema=schema,max_tokens=64))
        if expected not in result["answer"].casefold():
            raise RuntimeError("Local bilingual smoke test failed: "+lang)
        print("[LOCAL SMOKE PASS]",tier,lang,flush=True)
    # Exercise actual narration-shaped output and literal source evidence,
    # not only arithmetic or a mocked provider.
    scene_schema={"type":"object","properties":{"narration":{"type":"string"},
        "visual_search_query":{"type":"string"},"source_quote":{"type":"string"}},
        "required":["narration","visual_search_query","source_quote"],"additionalProperties":False}
    source="Ocean surface waves are commonly generated by wind transferring energy to the water."
    for lang in ("en","de"):
        started=time.monotonic()
        answer=json.loads(instance(tier).complete([{"role":"system","content":"Return only JSON. Quote the supplied source verbatim. Do not invent facts."},
            {"role":"user","content":f"Write one short educational narration in {lang}, an English video search query and a literal quote from this source: {source}"}],
            schema=scene_schema,max_tokens=350))
        if answer["source_quote"] not in source or len(answer["source_quote"])<15 or len(answer["narration"].split())<8 or not answer["visual_search_query"].strip():
            raise RuntimeError("Narration/source quote smoke failed "+lang)
        print("[LOCAL NARRATION PASS]",tier,lang,"seconds",round(time.monotonic()-started,1),flush=True)
