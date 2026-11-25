import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from verified_library import remember, candidates, read_rows, public_url

class VerifiedLibraryTests(unittest.TestCase):
    def test_public_urls_only(self):
        self.assertTrue(public_url("https://example.org/video.mp4"))
        self.assertFalse(public_url("https://example.org/video.mp4?token=abc"))
        self.assertFalse(public_url("https://user:secret@example.org/video.mp4"))

    def test_reuse_is_candidate_not_approval(self):
        lic={"id":"CC0-1.0","url":"https://creativecommons.org/publicdomain/zero/1.0/",
             "source_page":"https://example.org/asset","creator":"example","attribution_required":False}
        item=SimpleNamespace(source="wikimedia-video",id="example",url="https://example.org/video.mp4",
            text="whale breaching ocean",extra={"license":lic,"download_evidence":{"mode":"full_download"}})
        spec=SimpleNamespace(object="whale",visual_search_query="whale breaching")
        class Registry:
            enabled=["wikimedia-video"]
            def _item(self,*args):
                return SimpleNamespace(extra={})
        with tempfile.TemporaryDirectory() as tmp,patch.dict("os.environ",{"PURFFLE_VERIFIED_LIBRARY":"1"}):
            path=Path(tmp)/"index.json"
            q={"width":1920,"height":1080,"duration":20}
            self.assertTrue(remember(path,item,spec,q))
            self.assertEqual(len(read_rows(path)),1)
            self.assertEqual(len(candidates(path,Registry(),spec,["whale breaching"],5,Registry.enabled)),1)
            self.assertEqual(candidates(path,Registry(),spec,["whale breaching"],25,Registry.enabled),[])
            item.url+="?token=abc"
            self.assertFalse(remember(path,item,spec,q))
            self.assertNotIn("token=abc",path.read_text())
            item.url="https://example.org/video.mp4"
            item.extra["license"]={**lic,"id":"PEXELS"}
            self.assertFalse(remember(path,item,spec,q))
