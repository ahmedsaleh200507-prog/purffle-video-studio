"""Regression tests: quiet local motion is not the same as a still image."""
import unittest
from PIL import Image,ImageDraw,ImageEnhance
from media_validation import localized_motion_evidence

def scene(offset=0):
    frame=Image.new("L",(192,192),80)
    draw=ImageDraw.Draw(frame)
    for x in range(0,192,12):
        draw.line((x,0,x,191),fill=110,width=2)
    # Small moving regions on a larger stationary landscape.
    draw.rectangle((48+offset,48,76+offset,76),fill=220)
    draw.rectangle((96+offset,96,124+offset,124),fill=180)
    return frame

class LocalMotionTests(unittest.TestCase):
    def test_real_local_motion(self):
        frames=[scene(x) for x in (0,3,1,4,2,5,3,6)]
        self.assertTrue(localized_motion_evidence(frames)["passed"])
    def test_frozen(self):
        self.assertFalse(localized_motion_evidence([scene()]*8)["passed"])
    def test_one_cut(self):
        self.assertFalse(localized_motion_evidence([scene()]*7+[scene(12)])["passed"])
    def test_uniform_exposure(self):
        f=scene().point(lambda x:min(255,x+8))
        self.assertFalse(localized_motion_evidence([scene(),f]*4)["passed"])

if __name__=="__main__": unittest.main()
