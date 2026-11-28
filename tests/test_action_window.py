import unittest
from unittest.mock import patch
from action_window import select_window

class ActionWindowTests(unittest.TestCase):
    def test_later_window_uses_real_offset(self):
        def inspect(path,need,focus,contract,**kwargs):
            return {"verified":kwargs["frames"][0]>=3,"best_action_margin":.05}
        with patch("visual_director._frame_at", side_effect=lambda path,t,focus:t):
            result=select_window("clip",20.,5.,{"event_required":True},scorer=None,
                deadline=10**12,inspector=inspect)
        self.assertEqual(result["offset"],3.)
        self.assertEqual(result["state"],"later_interval_proposed")
    def test_no_event_keeps_start(self):
        self.assertEqual(select_window("clip",20.,5.,{},scorer=None,deadline=0)["offset"],0)
    def test_failed_event_keeps_start(self):
        with patch("visual_director._frame_at",return_value=None):
            result=select_window("clip",20.,5.,{"event_required":True},scorer=None,
                deadline=10**12,inspector=lambda *a,**k:{"verified":False})
        self.assertEqual(result["offset"],0)
        self.assertEqual(len(result["attempts"]),6)

    def test_late_action_and_bad_preview(self):
        def frame(path,t,focus):
            if t < 1: raise RuntimeError("bad first frame")
            return t
        def inspect(path,need,focus,contract,**kwargs):
            return {"verified":kwargs["frames"][0]>65,"best_action_margin":.05}
        with patch("visual_director._frame_at", side_effect=frame):
            result=select_window("clip",100.,5.,{"event_required":True},
                scorer=None,deadline=10**12,inspector=inspect)
        self.assertEqual(result["state"],"later_interval_proposed")
        self.assertGreater(result["offset"],65.)
        self.assertLessEqual(len(result["attempts"]),6)
        self.assertEqual(result["attempts"][0]["error_type"],"RuntimeError")

    def test_nonopening_scene_uses_nonopening_contract(self):
        def inspect(*args,**kwargs):
            self.assertFalse(kwargs["opening"])
            return {"verified":True}
        with patch("visual_director._frame_at",return_value=1):
            result=select_window("clip",20.,5.,{"event_required":True},
                scorer=None,deadline=10**12,inspector=inspect,opening=False)
        self.assertEqual(result["state"],"keep_start")
