import unittest
from video_first_policy import media_mix,contrast_prompts,check_topic_metadata
class VideoFirstTests(unittest.TestCase):
    def test_duration_not_count(self):
        m=media_mix([{"media_type":"video","screen_seconds":9},{"media_type":"photo","screen_seconds":1}])
        self.assertTrue(m["target_met"])
        self.assertEqual(m["video_share"],.9)
    def test_photo_heavy_report(self):
        m=media_mix([{"media_type":"video","screen_seconds":2},{"media_type":"photo","screen_seconds":8}])
        self.assertFalse(m["target_met"])
        self.assertFalse(m["video_majority"])
    def test_whale_negatives(self):
        self.assertTrue(any("no marine animal" in x for x in contrast_prompts("whale","humpback whale swimming")))
if __name__=="__main__":unittest.main()
