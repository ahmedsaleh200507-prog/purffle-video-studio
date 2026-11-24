import os
import tempfile
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch
from portrait_layout import plan_portrait,render_center_sample,center_filter
from media_validation import QualityValidator

class PortraitTests(unittest.TestCase):
    def test_center_and_upscale(self):
        with patch.dict(os.environ,{"PURFFLE_SHORTS_CENTER_CROP":"1"}):
            for w,h in [(1080,1920),(3840,2160),(1280,720),(1920,1080)]:
                p=plan_portrait(w,h,1080,1920)
                self.assertEqual(p["mode"],"center_crop")
            p=plan_portrait(1280,720,1080,1920)
            self.assertAlmostEqual(p["crop_scale"],1920/720,places=4)
            self.assertEqual(p["effective_source_width"],405)
            self.assertFalse(p["native_fullscreen"])
            self.assertIsNone(plan_portrait(640,360,1080,1920))
    def test_strict_legacy_mode(self):
        with patch.dict(os.environ,{"PURFFLE_SHORTS_CENTER_CROP":"0"}):
            self.assertIsNone(plan_portrait(1280,720,1080,1920))
    def test_render_real_frames(self):
        with patch.dict(os.environ,{"PURFFLE_SHORTS_CENTER_CROP":"1"}), tempfile.TemporaryDirectory() as d:
            src=Path(d)/"source.mp4"
            subprocess.run(["ffmpeg","-y","-v","error","-f","lavfi","-i","testsrc2=size=1280x720:rate=25",
                "-t","4","-c:v","libx264","-threads","2","-preset","ultrafast",str(src)],check=True,timeout=60)
            p=plan_portrait(1280,720,1080,1920)
            out=render_center_sample(src,p,3)
            q=QualityValidator().validate(out)
            self.assertEqual((q["width"],q["height"]),(1080,1920))
            self.assertGreaterEqual(q["duration"],2.9)
            self.assertIn("(iw-ow)/2",center_filter(1080,1920))
            self.assertNotIn("blur",center_filter(1080,1920))
if __name__=="__main__": unittest.main()
