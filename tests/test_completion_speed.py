import tempfile
import unittest
from pathlib import Path
from PIL import Image
from visual_score_cache import ExactScoreCache
from reviewed_graphic import reviewed_graphic

class CompletionTests(unittest.TestCase):
    def test_exact_cache(self):
        cache=ExactScoreCache(2)
        a=Image.new("RGB",(16,16),"red")
        calls=[]
        def infer(images,captions):
            calls.append(1)
            return [[.25]*len(captions) for _ in images]
        r=cache.score([a],["target"],infer)
        r[0][0]=1.
        self.assertEqual(cache.score([a.copy()],["target"],infer),[[.25]])
        self.assertEqual(len(calls),1)
        cache.score([a],["other"],infer)
        a.putpixel((0,0),(0,0,0))
        cache.score([a],["target"],infer)
        self.assertEqual(len(calls),3)
    def test_review_graphic_is_not_stock(self):
        with tempfile.TemporaryDirectory() as d:
            path,credit=reviewed_graphic({"narration":"A reviewed sentence.","visual_subject":"Aurora"},1,d,"en")
            with Image.open(path) as im:
                self.assertEqual(im.size,(1080,1920))
            self.assertEqual(credit["media_type"],"illustration")
            self.assertEqual(credit["visual_check"],"not_real_footage")
            with self.assertRaises(ValueError):
                reviewed_graphic({},2,d,"en")
