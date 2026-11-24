import unittest
from types import SimpleNamespace
from video_sources import ProviderRegistry

class LocPolicyTests(unittest.TestCase):
    def registry(self,rights,restricted=False):
        page="https://www.loc.gov/item/test/"
        class Client:
            def get(self,url,params=None):
                if url==page:
                    return {"item":{"title":"Train in motion","rights_advisory":[rights]},
                            "resources":[{"download_restricted":restricted,"duration":20,
                             "files":[[{"url":"https://tile.loc.gov/example.mp4","mimetype":"video/mp4","width":1920,"height":1080}]]}]}
                return {"results":[{"id":page}]}
        return ProviderRegistry(MediaItem=lambda *a,**k:SimpleNamespace(source=a[0],id=a[1],kind=a[2],url=a[3],width=a[4],height=a[5],extra={},**k),client=Client())
    def test_explicit_pd(self):
        self.assertEqual(len(self.registry("This film is in the public domain.")._loc("train")),1)
    def test_ambiguous_rights_rejected(self):
        self.assertEqual(self.registry("No known restrictions.")._loc("train"),[])
        self.assertEqual(self.registry("Not in the public domain.")._loc("train"),[])
    def test_restricted_download_rejected(self):
        self.assertEqual(self.registry("This film is in the public domain.",True)._loc("train"),[])
if __name__=="__main__": unittest.main()
