import unittest
from unittest.mock import patch
from types import SimpleNamespace
from crop_subject_policy import verify_crop_subject
class CropTests(unittest.TestCase):
    def test_subject_present(self):
        spec=SimpleNamespace(main_character="",object="whale",visual_search_query="whale swimming")
        matcher=SimpleNamespace(threshold=.23,_similarities=lambda f,c:[[.27,.24,.15,.11],[.26,.25,.14,.10],[.15,.14,.23,.1]])
        with patch("media_validation.scene_specific_hard_negatives",return_value=[]):
            self.assertEqual(verify_crop_subject([1,2,3],spec,matcher)["matching_frames"],2)
    def test_empty_crop_rejected(self):
        spec=SimpleNamespace(main_character="",object="whale",visual_search_query="whale swimming")
        matcher=SimpleNamespace(threshold=.23,_similarities=lambda f,c:[[.16,.14,.28,.1]]*3)
        with patch("media_validation.scene_specific_hard_negatives",return_value=[]):
            with self.assertRaises(ValueError):
                verify_crop_subject([1,2,3],spec,matcher)
if __name__=="__main__":unittest.main()
