import unittest
import tempfile
from concurrent.futures import ThreadPoolExecutor
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
    def test_parallel_writers_keep_matching_file_and_metadata(self):
        with tempfile.TemporaryDirectory() as d:
            c=Checkpoint(d,"topic","en","rev")
            sources=[]
            for i in range(12):
                p=Path(d)/f"source-{i}.wav"
                p.write_bytes(f"audio-{i}".encode())
                sources.append(p)
            def save(i):
                return c.store_file("voice",["same"],sources[i],{"index":i})
            with ThreadPoolExecutor(max_workers=6) as pool:
                results=list(pool.map(save,range(12)))
            self.assertEqual(len(set(results)),12)
            path,metadata=c.get_file("voice",["same"],".wav")
            self.assertEqual(path.read_bytes(),sources[metadata["index"]].read_bytes())
            self.assertFalse(list(c.root.glob("*.part")))

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
