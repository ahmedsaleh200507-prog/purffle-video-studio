import unittest
from dataclasses import dataclass
from types import SimpleNamespace
from short_caption_style import SETTINGS,lock_settings,install_style
@dataclass
class Settings:
    caption_style:str="neon"
    caption_position:str="lower"
    caption_font:str="other.ttf"
    caption_fontsize:int=150
    caption_max_words:int=6
    caption_uppercase:bool=False
    caption_emphasis:bool=True
    caption_emoji:bool=True
    language:str="de"
    width:int=1080
    height:int=1920
    unrelated:str="unchanged"
class CaptionPolicyTests(unittest.TestCase):
    def test_fixed_settings(self):
        s=lock_settings(Settings())
        for k,v in SETTINGS.items(): self.assertEqual(getattr(s,k),v)
        self.assertEqual(s.unrelated,"unchanged")
    def test_palette_and_position(self):
        overlays=SimpleNamespace(CAPTION_STYLES={},CENTER_Y={},CapStyle=lambda **kw:kw,
                                needs_ass=lambda s:True)
        install_style(overlays)
        style=overlays.CAPTION_STYLES["bold"]
        self.assertEqual(style["font"],"anton")
        self.assertEqual(style["active"],"#FFE11A")
        self.assertEqual(style["fill"],"#FFFFFF")
        self.assertEqual(style["stroke"],"#000000")
        self.assertIsNone(style["emphasis"])
        self.assertFalse(style["pop"])
        self.assertEqual(overlays.CENTER_Y["center"],.56)
        self.assertFalse(overlays.needs_ass(Settings()))
        self.assertTrue(overlays.needs_ass(Settings(width=1920,height=1080)))
if __name__=="__main__":unittest.main()
