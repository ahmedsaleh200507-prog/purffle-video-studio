import unittest
from object_framing import stable_focus,group_focus,track_focus
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
    def test_ambiguous_group_framing_preserves_both_subjects(self):
        rows=[[box(.70,.78),box(.81,.88)]]*3
        self.assertEqual(track_focus(rows,[0,1,2],.32)["state"],"ambiguous_identity")
        result=group_focus(rows,.32)
        self.assertEqual(result["state"],"proposed")
        self.assertGreater(result["proposed_group_coverage"],.95)
        self.assertGreater(result["focus_x"],.70)
    def test_widely_separated_group_does_not_jump(self):
        rows=[[box(.1,.2),box(.8,.9)],[box(.8,.9),box(.1,.2)],[box(.1,.2),box(.8,.9)]]
        # A static group proposal may cover one side but never becomes a track.
        self.assertNotIn("keyframes",group_focus(rows,.32))
        self.assertEqual(track_focus(rows,[0,1,2],.32)["state"],"ambiguous_identity")
    def test_single_detection_not_group(self):
        self.assertEqual(group_focus([[box(.8,.9)]]*3,.32)["state"],"insufficient_group_evidence")
if __name__=="__main__":unittest.main()
