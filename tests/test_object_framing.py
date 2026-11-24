import unittest
from object_framing import stable_focus
from portrait_layout import focus_filter
def box(x0,x1,score=.8): return {"box":[x0,.2,x1,.8],"score":score}
class FramingTests(unittest.TestCase):
    def test_right_subject(self):
        result=stable_focus([[box(.75,.88)],[box(.76,.92)],[box(.77,.91)]],.32)
        self.assertEqual(result["state"],"proposed")
        self.assertGreater(result["focus_x"],.7)
        self.assertGreater(result["proposed_box_coverage"],.95)
    def test_single_detection_cannot_move_crop(self):
        self.assertEqual(stable_focus([[box(.8,.9)],[],[]],.32)["state"],"insufficient_detections")
    def test_center_subject_stays(self):
        self.assertEqual(stable_focus([[box(.45,.55)]]*3,.32)["state"],"keep_default")
    def test_render_same_focus(self):
        self.assertIn("iw*0.80000",focus_filter(1080,1920,.8))
if __name__=="__main__":unittest.main()
