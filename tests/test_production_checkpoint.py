import unittest
import tempfile
from pathlib import Path
from production_checkpoint import Checkpoint

class CheckpointTests(unittest.TestCase):
    def test_resume_exact_identity(self):
        with tempfile.TemporaryDirectory() as d:
            c=Checkpoint(d,"Amazon","en","rev1")
            c.put("script",["Amazon","en"],[{"narration":"approved"}])
            self.assertEqual(Checkpoint(d,"Amazon","en","rev1").get("script",["Amazon","en"]),[{"narration":"approved"}])
            self.assertIsNone(Checkpoint(d,"Amazon","de","rev1").get("script",["Amazon","en"]))
            self.assertIsNone(Checkpoint(d,"Amazon","en","rev2").get("script",["Amazon","en"]))
    def test_corruption_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"test.wav";p.write_bytes(b"test audio")
            c=Checkpoint(d,"topic","en","rev")
            saved=c.store_file("voice-01",["sentence"],p,{"duration":30})
            self.assertIsNotNone(c.get_file("voice-01",["sentence"],".wav"))
            self.assertIsNone(c.get_file("voice-01",["different sentence"],".wav"))
            saved.write_bytes(b"bad")
            self.assertIsNone(c.get_file("voice-01",["sentence"],".wav"))
if __name__=="__main__": unittest.main()
