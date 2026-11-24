import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from long_still_recovery import verify_photo,stills

class PhotoPolicyTests(unittest.TestCase):
    def test_reject_unrelated_photo(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"sample.png"
            Image.new("RGB",(720,720),"green").save(p)
            class Matcher:
                def _similarities(self,*args): return [[.14,.13,.35,.1,.1,.1]]
            with self.assertRaises(ValueError):
                verify_photo(p,"robot","industrial robot",Matcher())
    def test_accept_matching_photo(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"sample.png"
            Image.new("RGB",(720,720),"green").save(p)
            class Matcher:
                def _similarities(self,*args): return [[.32,.29,.15,.12,.1,.15]]
            self.assertEqual(verify_photo(p,"robot","industrial robot",Matcher())["visual_check"],"local_clip_photo_screening")
    def test_no_generated_filler_in_strict_mode(self):
        with tempfile.TemporaryDirectory() as d, patch("long_still_recovery.commons",return_value=[]), patch("long_still_recovery.pixabay",return_value=[]):
            with self.assertRaises(RuntimeError):
                stills({"visual_subject":"robot","visual_search_query":"robot"},1,Path(d),set(),require_verified=True,matcher=object())
if __name__=="__main__": unittest.main()
