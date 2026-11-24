import unittest
from types import SimpleNamespace
from video_sources import ProviderRegistry

PD="https://creativecommons.org/publicdomain/zero/1.0/"
def media(name,w=None,h=None,size=12000000,source="original"):
    return {"name":name,"width":w,"height":h,"size":size,"source":source,"length":"00:03:20"}
def registry(items):
    class Client:
        def get(self,url,params=None):
            if "advancedsearch.php" in url:
                return {"response":{"docs":[{"identifier":k,"title":v["metadata"]["title"]} for k,v in items.items()]}}
            return items[url.rsplit("/",1)[1]]
    return ProviderRegistry(MediaItem=lambda *a,**k:SimpleNamespace(source=a[0],id=a[1],kind=a[2],url=a[3],width=a[4],height=a[5],extra={},**k),client=Client())
def entry(title,files,license=PD):
    return {"metadata":{"title":title,"licenseurl":license},"files":files}

class ArchiveHDTests(unittest.TestCase):
    def test_native_hd_and_variants(self):
        r=registry({"volcano":entry("Volcano eruption",[media("small.mp4",640,360),media("full.mov",1920,1080,900000000),media("hd.mp4",1280,720),media("preview.mp4",3840,2160)])})
        item=r._archive("volcano")[0]
        self.assertEqual((item.width,item.height),(1920,1080))
        self.assertTrue(item.url.endswith("full.mov"))
        self.assertEqual(len(item.extra["download_variants"]),1)
        self.assertTrue(item.extra["download_variants"][0].endswith("hd.mp4"))
        self.assertEqual(item.duration,200)
    def test_known_sd_skipped(self):
        self.assertEqual(registry({"sd":entry("Volcano",[media("sd.mp4",640,480)])})._archive("volcano"),[])
    def test_gameplay_excluded(self):
        self.assertEqual(registry({"game":entry("Sega longplay gameplay",[media("game.mp4",1920,1080)])})._archive("volcano"),[])
    def test_unknown_dimensions_not_faked(self):
        item=registry({"unknown":entry("Volcano",[media("original.mp4")])})._archive("volcano")[0]
        self.assertEqual((item.width,item.height),(0,0))
        self.assertFalse(item.extra["archive_variant_evidence"][0]["known_hd"])
    def test_license_kept(self):
        self.assertEqual(registry({"bad":entry("Volcano",[media("full.mp4",1920,1080)],"https://creativecommons.org/licenses/by/4.0/")})._archive("volcano"),[])
if __name__=="__main__": unittest.main()
