import unittest
from types import SimpleNamespace
from long_sentence_plan import timed_groups,validate_plan
class TimedPlanTests(unittest.TestCase):
    def test_actual_boundary(self):
        text="Ocean waves move. Wind transfers energy to water."
        words=[SimpleNamespace(text=w,start=t) for w,t in zip(text.split(),[0,.5,1,4,5,6,7,8])]
        groups=timed_groups(text,words,10)
        self.assertEqual(groups[0]["end_frame"],120)
        self.assertEqual(groups[1]["start_frame"],120)
        self.assertEqual(groups[1]["end_frame"],300)
        self.assertEqual(" ".join(x["narration"] for x in groups),text)
    def test_alignment_mismatch(self):
        with self.assertRaises(ValueError):
            timed_groups("The ocean.",[SimpleNamespace(text="wrong",start=0)],4)
    def test_invented_location(self):
        g=[{"index":1,"narration":"Waves break on the coast.","start_frame":0,"end_frame":120,"seconds":4}]
        p={"shots":[{"index":1,"visual_subject":"ocean waves","visual_search_query":"ocean waves Hawaii","location":"Hawaii"}]}
        with self.assertRaises(ValueError):
            validate_plan(p,g,{},"Ocean waves")
    def test_preserve_location(self):
        g=[{"index":1,"narration":"Amazon rainforest trees.","start_frame":0,"end_frame":120,"seconds":4}]
        p={"shots":[{"index":1,"visual_subject":"trees","visual_search_query":"rainforest trees","location":""}]}
        self.assertEqual(validate_plan(p,g,{},"Amazon rainforest")[0]["required_regions"],["amazon"])
if __name__=="__main__":unittest.main()
