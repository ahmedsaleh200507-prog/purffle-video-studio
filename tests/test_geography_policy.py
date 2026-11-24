import unittest
from geography_policy import scene_requirement,require_geography,scoped_queries

class GeographyTests(unittest.TestCase):
    def test_amazon_not_generic_forest(self):
        required=scene_requirement({"object":"forest"},"Amazon rainforest")
        self.assertEqual(required,["amazon"])
        for metadata in ("pine forest Europe","Brazil forest","rainforest"):
            with self.assertRaises(ValueError): require_geography(required,metadata)
        self.assertTrue(require_geography(required,"Amazon rainforest Brazil")["accepted"])
    def test_conflict(self):
        with self.assertRaises(ValueError):
            require_geography(["amazon"],"Amazon rainforest European Alps")
    def test_scene_overrides_topic(self):
        self.assertEqual(scene_requirement({"location":"Vienna"},"History of Europe"),["vienna"])
    def test_queries_keep_location(self):
        self.assertEqual(scoped_queries(["river"],["amazon"]),["Amazon rainforest river"])
    def test_non_geographic(self):
        self.assertTrue(require_geography(scene_requirement({"object":"robot"},"How robots work"),"industrial robot Japan")["accepted"])
    def test_german(self):
        self.assertEqual(scene_requirement({},"Der Amazonas-Regenwald"),["amazon"])
if __name__=="__main__": unittest.main()
