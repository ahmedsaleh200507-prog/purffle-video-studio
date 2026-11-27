import unittest
from PIL import Image
from object_region_review import corroborate

class RegionReviewTests(unittest.TestCase):
    def test_independent_screening(self):
        image=Image.new("RGB",(200,200))
        boxes=[{"box":[.1,.1,.4,.4],"score":.9},{"box":[.5,.5,.8,.8],"score":.95}]
        def scores(crops,prompts):
            return [[.30]+[.12]*(len(prompts)-1),[.20]+[.27]*(len(prompts)-1)]
        result=corroborate(image,"person",boxes,scores)
        self.assertEqual(result["accepted"],boxes[:1])
        self.assertFalse(result["checks"][1]["accepted"])
    def test_empty_no_inference(self):
        self.assertEqual(corroborate(Image.new("RGB",(40,40)),"whale",[])["accepted"],[])
    def test_no_shape_mismatch_pass(self):
        with self.assertRaises(ValueError):
            corroborate(Image.new("RGB",(100,100)),"cat",[{"box":[.1,.1,.8,.8],"score":.9}],lambda a,b:[])

    def test_invalid_detector_rows_never_reach_clip(self):
        image=Image.new("RGB",(200,200))
        boxes=[{"box":[.1,.1,.4,.4],"score":v} for v in (float("nan"),float("inf"),-.1,1.1,.1,None)]
        boxes += [None,{"box":None,"score":.9},{"box":["bad",.1,.4,.4],"score":.9}]
        def fail(*args):
            self.fail("Invalid region passed to inference")
        self.assertEqual(corroborate(image,"cat",boxes,fail)["accepted"],[])
