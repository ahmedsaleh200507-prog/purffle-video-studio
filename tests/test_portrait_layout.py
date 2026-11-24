import tempfile
import subprocess
import unittest
from pathlib import Path
from portrait_layout import plan_portrait,render_context
from media_validation import QualityValidator

class PortraitTests(unittest.TestCase):
    def test_native_and_4k(self):
        self.assertEqual(plan_portrait(1080,1920,1080,1920)["mode"],"subject_crop")
        self.assertEqual(plan_portrait(3840,2160,1080,1920)["mode"],"subject_crop")
    def test_preserve_720(self):
        p=plan_portrait(1280,720,1080,1920)
        self.assertEqual(p["mode"],"full_frame_context")
        self.assertLessEqual(p["foreground_scale"],1)
        self.assertIsNone(plan_portrait(640,360,1080,1920))
        self.assertIsNone(plan_portrait(1280,720,1080,1920,allow_context=False))
    def test_render_real_frames(self):
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/"source.mp4"
            subprocess.run(["ffmpeg","-y","-v","error","-f","lavfi","-i","testsrc2=size=1280x720:rate=25",
                "-t","4","-c:v","libx264","-threads","2","-preset","ultrafast",str(src)],check=True,timeout=60)
            p=plan_portrait(1280,720,1080,1920)
            out=render_context(src,p,3)
            q=QualityValidator().validate(out)
            self.assertEqual((q["width"],q["height"]),(1080,1920))
            self.assertGreaterEqual(q["duration"],2.9)
if __name__=="__main__": unittest.main()
