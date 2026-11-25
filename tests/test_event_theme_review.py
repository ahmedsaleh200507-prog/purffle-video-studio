import unittest
from unittest.mock import patch
from PIL import Image,ImageDraw
from visual_director import visual_scores
from event_theme_review import compare,motion_pair,observe

CONTRACT={"family":"breaching","event_required":True}
class EventThemeTests(unittest.TestCase):
    def test_split_scores_not_accepted(self):
        self.assertFalse(visual_scores(CONTRACT,[[.30,.31],[.20,.10]])["verified"])
    def test_same_frame_accepted(self):
        self.assertTrue(visual_scores(CONTRACT,[[.30,.20],[.20,.30]])["verified"])
    def test_motion_not_uniform_exposure(self):
        a=Image.new("RGB",(96,96),(40,40,40))
        self.assertFalse(motion_pair(a,a)["localized_change_observed"])
        self.assertFalse(motion_pair(a,Image.new("RGB",(96,96),(80,80,80)))["localized_change_observed"])
        b=a.copy()
        ImageDraw.Draw(b).rectangle((20,20,50,50),fill="white")
        self.assertTrue(motion_pair(a,b)["localized_change_observed"])
    def test_independent_agreement_is_not_acceptance(self):
        self.assertFalse(compare([[0,1],[2,1]],2)["agrees"])
        with patch.dict("os.environ",{"PURFFLE_EVENT_THEME_REVIEW":"1"}):
            with patch("event_theme_review._COUNTS",{"event":0,"theme":0}):
                result=observe("theme",[1,2],["target","negative"],lambda a,b:[[0,1],[0,1]])
                self.assertEqual(result["state"],"observed")
                self.assertFalse(result["agrees"])
                self.assertNotIn("verified",result)
                for _ in range(5):
                    observe("theme",[1],["a","b"],lambda a,b:[[1,0]])
                self.assertEqual(observe("theme",[1],["a","b"],lambda a,b:[[1,0]])["state"],"budget_exhausted")
