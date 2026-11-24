import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from short_recovery import save_reviewed_script,recover_approved_dossier

class ShortRecoveryPolicy(unittest.TestCase):
    def test_script_preserves_geographic_context(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"reviewed-script.json"
            scene=SimpleNamespace(narration="The Amazon is a vast rainforest.",
                object="forest",location="Amazon rainforest",action="ambient",time="",main_character="",
                visual_search_query="Amazon rainforest aerial")
            save_reviewed_script(SimpleNamespace(scenes=[scene]),"en","Amazon rainforest",path)
            self.assertEqual(json.loads(path.read_text())["scenes"][0]["location"],"Amazon rainforest")
    def test_unknown_topic_never_invents_offline_facts(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(RuntimeError):
                recover_approved_dossier("Unverified xyz experiment 784", "en",Path(d))
            self.assertFalse((Path(d)/"reviewed-script.json").exists())
if __name__=="__main__": unittest.main()
