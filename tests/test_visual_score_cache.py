import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from PIL import Image
from visual_score_cache import ExactScoreCache

class VisualScoreCacheTests(unittest.TestCase):
    def test_concurrent_inference_is_coalesced(self):
        cache=ExactScoreCache()
        frames=[Image.new("RGB",(8,8))]
        barrier=threading.Barrier(6)
        calls=[]
        def infer(*args):
            calls.append(1)
            time.sleep(.05)
            return [[.5]]
        def score(_):
            barrier.wait(timeout=5)
            return cache.score(frames,["cat"],infer)
        with ThreadPoolExecutor(max_workers=6) as pool:
            results=list(pool.map(score,range(6)))
        self.assertEqual(results,[[[.5]]]*6)
        self.assertEqual(len(calls),1)
        self.assertEqual(cache.hits,5)
        results[0][0][0]=0
        self.assertEqual(cache.score(frames,["cat"],infer),[[.5]])

    def test_failure_does_not_poison_cache(self):
        cache=ExactScoreCache()
        frames=[Image.new("RGB",(8,8))]
        def fail(*args):
            raise RuntimeError("failed inference")
        with self.assertRaises(RuntimeError):
            cache.score(frames,["cat"],fail)
        self.assertEqual(cache.score(frames,["cat"],lambda *a:[[.7]]),[[.7]])
        self.assertFalse(cache._pending)
