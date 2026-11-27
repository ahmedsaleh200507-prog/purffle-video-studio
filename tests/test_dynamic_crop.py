import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from PIL import Image
from dynamic_crop import tracking_filter, render_tracked

PROPOSAL={"state":"shadow_proposal","keyframes":[{"time":.1,"focus_x":.20},
    {"time":2.,"focus_x":.50},{"time":3.8,"focus_x":.80}],
    "min_tracked_coverage":1.,"tracked_coverage":1.,"fixed_coverage":.4}

class DynamicCropTests(unittest.TestCase):
    def test_invalid_track(self):
        with self.assertRaises(ValueError):
            tracking_filter(180,320,{"state":"ambiguous_identity"},4.)
    def test_invalid_coverage(self):
        for field in ("min_tracked_coverage", "tracked_coverage", "fixed_coverage"):
            for value in (float("nan"), float("inf"), -1, 2):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    tracking_filter(180,320,{**PROPOSAL, field:value},4.)
    def test_unsafe_speed(self):
        bad={**PROPOSAL,"keyframes":[{"time":.1,"focus_x":.1},{"time":.2,"focus_x":.8},{"time":3.8,"focus_x":.8}]}
        with self.assertRaises(ValueError):
            tracking_filter(180,320,bad,4.)
    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),"FFmpeg needed")
    def test_real_render_follows_moving_marker(self):
        # Synthetic moving red subject on a landscape clip, real FFmpeg encoding.
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"source.mp4"
            frames=bytearray()
            for i in range(100):
                im=Image.new("RGB",(640,360),(30,70,105))
                from PIL import ImageDraw
                x=round(640*(.2+.6*i/99))
                ImageDraw.Draw(im).rectangle((x-20,150,x+20,210),fill=(245,10,10))
                frames.extend(im.tobytes())
            subprocess.run(["ffmpeg","-y","-v","error","-f","rawvideo","-pix_fmt","rgb24",
                "-s","640x360","-r","25","-i","-","-c:v","libx264","-pix_fmt","yuv420p",
                "-threads","2",str(path)],input=bytes(frames),check=True,timeout=30)
            derived=render_tracked(path,PROPOSAL,4.,180,320,deadline=time.monotonic()+90)
            for t in (.2,2.,3.7):
                data=subprocess.check_output(["ffmpeg","-v","error","-ss",str(t),"-i",str(derived),
                    "-frames:v","1","-f","rawvideo","-pix_fmt","rgb24","-"],timeout=10)
                im=Image.frombytes("RGB",(180,320),data)
                xs=[i%180 for i,(r,g,b) in enumerate(im.getdata()) if r>170 and g<70 and b<70]
                self.assertGreater(len(xs),500)
                self.assertLess(abs(sum(xs)/len(xs)-90),25)
