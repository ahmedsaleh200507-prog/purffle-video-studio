"""Bounded process-local exact image/text score reuse. No disk or API calls."""
from collections import OrderedDict
import hashlib
import math
import threading

class ExactScoreCache:
    def __init__(self,max_entries=96):
        self.max_entries=max(1,min(128,int(max_entries)))
        self._rows=OrderedDict()
        self._lock=threading.RLock()
        self.hits=0
        self.misses=0
    def _key(self,images,captions):
        if not images or not captions or len(images)>24 or len(captions)>64:
            return None
        keys=[]
        for im in images:
            if im.width*im.height>2_000_000:
                return None
            keys.append((im.mode,im.size,hashlib.sha256(im.tobytes()).digest()))
        return tuple(keys),tuple(captions)
    def score(self,images,captions,infer):
        key=self._key(images,captions)
        if key is not None:
            with self._lock:
                if key in self._rows:
                    self.hits+=1
                    self._rows.move_to_end(key)
                    return [list(row) for row in self._rows[key]]
                self.misses+=1
        result=infer(images,captions)
        if key is not None and len(result)==len(images) and all(
                len(row)==len(captions) and all(math.isfinite(float(x)) for x in row) for row in result):
            with self._lock:
                self._rows[key]=tuple(tuple(float(x) for x in row) for row in result)
                self._rows.move_to_end(key)
                while len(self._rows)>self.max_entries:
                    self._rows.popitem(last=False)
        return result
