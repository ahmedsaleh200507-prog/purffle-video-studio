import unittest
from era_policy import scene_era,source_allowed,footage_allowed

class EraPolicyTests(unittest.TestCase):
    def test_modern_robots(self):
        era=scene_era({"visual_search_query":"modern industrial robots"})
        self.assertFalse(source_allowed("loc-video",era))
        self.assertFalse(footage_allowed("archive-video",era,"archival footage of a factory"))
        self.assertTrue(footage_allowed("pixabay",era,"robot factory"))
    def test_unspecified(self):
        era=scene_era({"object":"factory","visual_search_query":"factory machinery"})
        self.assertFalse(source_allowed("loc-video",era))
    def test_historical(self):
        era=scene_era({"visual_search_query":"historic factory in 1904"})
        self.assertTrue(source_allowed("loc-video",era))
        self.assertTrue(footage_allowed("loc-video",era,"factory","1904"))
        self.assertFalse(footage_allowed("loc-video",era,"factory","1939"))
        self.assertFalse(footage_allowed("loc-video",era,"factory",""))
    def test_decade(self):
        era=scene_era({"visual_search_query":"1920s city street"})
        self.assertTrue(footage_allowed("loc-video",era,"city","1925"))
        self.assertFalse(footage_allowed("loc-video",era,"city","1904"))
    def test_today_with_history(self):
        era=scene_era({"title":"Modern factories today compared with 1904","object":"factory"})
        self.assertFalse(source_allowed("loc-video",era))
if __name__=="__main__": unittest.main()
