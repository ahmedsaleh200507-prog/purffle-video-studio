import unittest
from unittest.mock import patch
import visual_language_review as review

class VisualLanguageReviewTests(unittest.TestCase):
    def setUp(self):
        self.counts = patch.object(review, "_COUNTS", {"florence": 0, "qwen": 0})
        self.failed = patch.object(review, "_FAILED", set())
        self.counts.start()
        self.failed.start()
        self.limits = patch.object(review, "_LIMITS", {"florence": 2, "qwen": 1})
        self.limits.start()
        self.addCleanup(self.limits.stop)
        self.addCleanup(self.counts.stop)
        self.addCleanup(self.failed.stop)

    def test_disabled_does_not_infer(self):
        with patch.dict("os.environ", {"PURFFLE_VLM_SHADOW":"0"}), patch.object(review, "_infer") as infer:
            self.assertEqual(review.observe([1], "cat", "sleeping cat")["state"], "disabled")
            infer.assert_not_called()

    def test_bounded_and_center_frame(self):
        with patch.dict("os.environ", {"PURFFLE_VLM_SHADOW":"1", "PURFFLE_VLM_FRAMES":"1"}), patch.object(review, "_infer", return_value="cat") as infer:
            result = review.observe([1,2,3], "cat", "sleeping cat")
            self.assertEqual(result["models"]["qwen"]["state"], "observed")
            infer.assert_any_call("qwen", 2)
            second = review.observe([1], "cat", "cat")
            self.assertEqual(second["models"]["qwen"]["state"], "budget_exhausted")
            third = review.observe([1], "cat", "cat")
            self.assertEqual(third["models"]["florence"]["state"], "budget_exhausted")
            self.assertEqual(infer.call_count, 3)

    def test_multi_frame_batches_and_budget(self):
        env = {"PURFFLE_VLM_SHADOW": "1", "PURFFLE_VLM_FRAMES": "3",
               "PURFFLE_VLM_FLORENCE_BUDGET": "5", "PURFFLE_VLM_QWEN_BUDGET": "2"}
        with patch.dict("os.environ", env), patch.object(review, "_infer_many", side_effect=lambda key, frames: [str(f) for f in frames]) as infer:
            result = review.observe([1,2,3,4,5], "cat", "sleeping cat")
            self.assertEqual(result["models"]["florence"]["sample_indices"], [0,2,4])
            self.assertEqual(result["models"]["qwen"]["sample_indices"], [0,4])
            self.assertEqual(result["models"]["florence"]["samples"][1]["caption"], "3")
            second = review.observe([1,2,3], "cat", "cat")
            self.assertEqual(second["models"]["florence"]["sample_indices"], [0,2])
            self.assertEqual(second["models"]["qwen"]["state"], "budget_exhausted")
            self.assertEqual(infer.call_count, 3)
            self.assertEqual(review._COUNTS, {"florence": 5, "qwen": 2})

    def test_failure_is_non_blocking_and_not_retried(self):
        with patch.dict("os.environ", {"PURFFLE_VLM_SHADOW":"1"}), patch.object(review, "_infer", side_effect=RuntimeError) as infer:
            result = review.observe([1], "cat", "cat")
            self.assertEqual(result["state"], "shadow_only")
            self.assertEqual(result["models"]["florence"]["state"], "unavailable")
            review.observe([1], "cat", "cat")
            self.assertEqual(infer.call_count, 2)

if __name__ == "__main__":
    unittest.main()
