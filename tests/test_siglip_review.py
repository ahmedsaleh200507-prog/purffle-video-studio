import unittest
from unittest.mock import patch
import siglip_review as review

class SiglipReviewTests(unittest.TestCase):
    def test_tie_does_not_agree(self):
        with patch("video_first_policy.contrast_prompts",return_value=[]), patch.object(review,"score",return_value=[[2,2,0,0],[0,0,2,2]]):
            self.assertFalse(review.check([1,2],"whale","whale breaching")["agrees"])

    def test_malformed_and_nonfinite_scores(self):
        for rows in ([],[[1,2]],[[1,2,0,float("nan")]],[[1,2,0,0],[1,2,0,0]]):
            with self.subTest(rows=rows), patch("video_first_policy.contrast_prompts",return_value=[]), patch.object(review,"score",return_value=rows):
                with self.assertRaises(ValueError):
                    review.check([1],"whale","whale breaching")
