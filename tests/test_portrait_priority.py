import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from footage_search import discover_portrait_first

def item(key,w,h):
    return SimpleNamespace(key=key,width=w,height=h)

class PriorityTests(unittest.TestCase):
    def test_cross_provider_portrait_first(self):
        landscape=item("wide",3840,2160)
        unknown=item("unknown",0,0)
        portrait=item("vertical",1080,1920)
        with patch("footage_search.discover",return_value=iter([
            ("pixabay",[landscape,unknown]),("nasa",[portrait])])):
            deferred=[]
            rows=list(discover_portrait_first(None,["pixabay","nasa"],["test"],time.monotonic()+60,deferred))
            self.assertEqual([r[2] for r in rows],["portrait","unknown_orientation","landscape_fallback"])
            self.assertEqual([r[1][0].key for r in rows],["vertical","unknown","wide"])
    def test_unknown_can_be_deferred(self):
        unknown=item("unknown",0,0)
        with patch("footage_search.discover",return_value=iter([("nasa",[unknown])])):
            deferred=[]
            gen=discover_portrait_first(None,["nasa"],["test"],time.monotonic()+60,deferred)
            self.assertEqual(next(gen)[2],"unknown_orientation")
            deferred.append(("nasa",unknown))
            self.assertEqual(next(gen)[2],"landscape_fallback")
    def test_landscape_only(self):
        with patch("footage_search.discover",return_value=iter([("usgs",[item("wide",1280,720)])])):
            rows=list(discover_portrait_first(None,["usgs"],["test"],time.monotonic()+60,[]))
            self.assertEqual([r[2] for r in rows],["landscape_fallback"])

if __name__=="__main__": unittest.main()
