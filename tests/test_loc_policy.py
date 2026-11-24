import unittest
from types import SimpleNamespace
from video_sources import ProviderRegistry

class LocPolicyTests(unittest.TestCase):
    def registry(self,rights,restricted=False,legacy=False,low=False):
        page="https://www.loc.gov/item/test/"
        class Client:
            def get(self,url,params=None):
                if url==page:
                    file={"url":"https://tile.loc.gov/example.mp4","mimetype":"video/mp4","width":1920,"height":1080}
                    if legacy:
                        file={"download":"//cdn.loc.gov/example.mp4","mimetype":"video/mp4","canDownload":True,"width":1920,"height":1080}
                    if low:
                        file.update(width=640,height=360)
                    return {"item":{"title":"Train in motion","rights_advisory":[rights]},
                            "resources":[{"download_restricted":restricted,"duration":20,"files":[[file]]}]}
                return {"results":[{"id":page.replace("https:","http:") if legacy else page}]}
        return ProviderRegistry(MediaItem=lambda *a,**k:SimpleNamespace(source=a[0],id=a[1],kind=a[2],url=a[3],width=a[4],height=a[5],extra={},**k),client=Client())
    def test_explicit_pd(self):
        self.assertEqual(len(self.registry("This film is in the public domain.")._loc("train")),1)
    def test_legacy_id_and_official_download_field(self):
        items=self.registry("This film is in the public domain.",legacy=True)._loc("train")
        self.assertEqual(items[0].url,"https://cdn.loc.gov/example.mp4")
    def test_ambiguous_rights_rejected(self):
        self.assertEqual(self.registry("No known restrictions.")._loc("train"),[])
        self.assertEqual(self.registry("Not in the public domain.")._loc("train"),[])
    def test_restricted_download_rejected(self):
        self.assertEqual(self.registry("This film is in the public domain.",True)._loc("train"),[])
    def test_low_resolution_rejected(self):
        self.assertEqual(self.registry("This film is in the public domain.",low=True)._loc("train"),[])
if __name__=="__main__": unittest.main()
