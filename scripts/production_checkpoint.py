"""Atomic production checkpoint scoped to topic, language and code revision."""
import hashlib
import json
import os
import shutil
from pathlib import Path
def digest(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda:stream.read(1024*1024),b""):
            h.update(block)
    return h.hexdigest()
def signature(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
def write(path,value):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+".part")
    temp.write_text(json.dumps(value,ensure_ascii=False,sort_keys=True),encoding="utf8")
    temp.replace(path)
def read(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf8"))
    except (OSError,ValueError,TypeError):
        return None
class Checkpoint:
    def __init__(self,root,topic,language,revision):
        self.identity=signature({"topic":topic,"language":language,"revision":revision,"schema":1})
        self.root=Path(root)/self.identity
        self.root.mkdir(parents=True,exist_ok=True)
    def get(self,key,identity):
        data=read(self.root/(key+".json"))
        if isinstance(data,dict) and data.get("identity")==signature(identity):
            return data.get("value")
        return None
    def put(self,key,identity,value):
        write(self.root/(key+".json"),{"identity":signature(identity),"value":value})
    def store_file(self,key,identity,source,metadata):
        source=Path(source)
        dest=self.root/(key+source.suffix)
        temp=dest.with_suffix(dest.suffix+".part")
        shutil.copyfile(source,temp)
        sha=digest(temp)
        temp.replace(dest)
        self.put(key,identity,{"name":dest.name,"sha256":sha,"metadata":metadata})
        return dest
    def get_file(self,key,identity,suffix):
        data=self.get(key,identity)
        if not isinstance(data,dict) or data.get("name")!=key+suffix:
            return None
        path=self.root/data["name"]
        if not path.is_file() or path.is_symlink() or digest(path)!=data.get("sha256"):
            return None
        return path,data.get("metadata",{})
def get_script_part(key,identity):
    root=os.getenv("PURFFLE_SCRIPT_CHECKPOINT")
    data=read(Path(root)/(key+".json")) if root else None
    return data.get("value") if isinstance(data,dict) and data.get("identity")==signature(identity) else None
def put_script_part(key,identity,value):
    root=os.getenv("PURFFLE_SCRIPT_CHECKPOINT")
    if root:
        write(Path(root)/(key+".json"),{"identity":signature(identity),"value":value})
