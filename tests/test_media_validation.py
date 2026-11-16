"""Local validation tests; generated FFmpeg fixtures are synthetic test inputs only."""
import io
import json
import socket
import subprocess
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from scripts.media_validation import (QualityValidator, SceneMatcher, SceneSpec, ValidationError,
                                      VideoDownloader)


class Reply(io.BytesIO):
    def __init__(self, raw=b"v" * 2048, headers=None, url="https://media.example/video.mp4"):
        super().__init__(raw)
        self.headers = headers or {"Content-Length": str(len(raw)), "Content-Type": "video/mp4"}
        self.url = url

    def geturl(self):
        return self.url


class Opener:
    def __init__(self, *replies):
        self.replies = iter(replies)
        self.calls = 0

    def open(self, request, timeout):
        self.calls += 1
        response = next(self.replies)
        if isinstance(response, Exception):
            raise response
        return response


class DownloaderTests(unittest.TestCase):
    def test_private_urls_rejected(self):
        with patch("socket.getaddrinfo", return_value=[(socket.AF_INET, 1, 6, "", ("127.0.0.1", 443))]):
            with self.assertRaises(ValidationError):
                VideoDownloader.validate_url("https://localhost/video.mp4")
        for url in ("http://media.example/a", "file:///tmp/a", "https://user:pw@media.example/a"):
            with self.assertRaises(ValidationError):
                VideoDownloader.validate_url(url)

    def test_mixed_public_private_dns_rejected(self):
        records = [(socket.AF_INET, 1, 6, "", (ip, 443)) for ip in ("8.8.8.8", "169.254.169.254")]
        with patch("socket.getaddrinfo", return_value=records), self.assertRaises(ValidationError):
            VideoDownloader.validate_url("https://media.example/a")

    @patch.object(VideoDownloader, "validate_url")
    def test_atomic_cache_digest_and_corruption_repair(self, validate):
        with tempfile.TemporaryDirectory() as root:
            opener = Opener(Reply(), Reply(b"b" * 2048))
            loader = VideoDownloader(Path(root), opener=opener)
            first = loader.download("https://media.example/video.mp4")
            self.assertEqual(first.read_bytes(), b"v" * 2048)
            self.assertEqual(loader.download("https://media.example/video.mp4"), first)
            self.assertEqual(opener.calls, 1)
            first.write_bytes(b"corrupted")
            self.assertEqual(loader.download("https://media.example/video.mp4").read_bytes(), b"b" * 2048)
            self.assertEqual(opener.calls, 2)
            self.assertFalse(list(Path(root).glob("*.part")))

    @patch.object(VideoDownloader, "validate_url")
    def test_http_errors_never_succeed(self, validate):
        with tempfile.TemporaryDirectory() as root:
            for status in (403, 404, 429, 500):
                opener = Opener(urllib.error.HTTPError("https://media.example/a", status, "error", {}, None))
                with self.subTest(status=status), self.assertRaisesRegex(ValidationError, str(status)):
                    VideoDownloader(root, opener=opener).download("https://media.example/a")
            self.assertFalse(list(Path(root).glob("*.bin")))

    def test_redirect_target_validated(self):
        error = urllib.error.HTTPError("https://media.example/a", 302, "redirect",
                                       {"Location": "https://127.0.0.1/private"}, None)
        with tempfile.TemporaryDirectory() as root:
            def gate(url):
                if "127.0.0.1" in url:
                    raise ValidationError("private redirect")
            with patch.object(VideoDownloader, "validate_url", side_effect=gate), self.assertRaisesRegex(ValidationError, "private"):
                VideoDownloader(root, opener=Opener(error)).download("https://media.example/a")

    @patch.object(VideoDownloader, "validate_url")
    def test_size_type_and_partial_body_rejected(self, validate):
        fixtures = [Reply(headers={"Content-Length": "99999"}),
                    Reply(headers={"Content-Type": "image/png"}),
                    Reply(headers={"Content-Length": "3000", "Content-Type": "video/mp4"}),
                    Reply(raw=b"v" * 5000, headers={"Content-Type": "video/mp4"})]
        for response in fixtures:
            with tempfile.TemporaryDirectory() as root:
                with self.assertRaises(ValidationError):
                    VideoDownloader(root, max_bytes=4096, opener=Opener(response)).download("https://media.example/a")
                self.assertFalse(list(Path(root).glob("*.part")))


class SceneTests(unittest.TestCase):
    def setUp(self):
        self.spec = SceneSpec.from_dict({"main_character": "young man", "object": "euro banknote",
                                        "action": "picking up", "location": "sidewalk", "time": "daylight",
                                        "visual_search_query": "young man picking up euro banknote on sidewalk"})
        self.metadata = "young man picking up euro banknote on sidewalk"

    def test_spec_requires_object_and_action(self):
        with self.assertRaises(ValidationError):
            SceneSpec.from_dict({"search_query": "money"})

    def test_unrelated_clip_rejected_before_model_or_download(self):
        for metadata in ("young man playing guitar on sidewalk", "electronic device on road", "man riding skateboard"):
            with self.subTest(metadata=metadata), patch.object(SceneMatcher, "_load") as load:
                with self.assertRaisesRegex(ValidationError, "grounding"):
                    SceneMatcher().match(Path("unused"), self.spec, metadata, duration=5)
                load.assert_not_called()

    def test_action_required_even_with_object_present(self):
        with self.assertRaisesRegex(ValidationError, "action"):
            SceneMatcher().match(Path("unused"), self.spec, "young man holding euro banknote on sidewalk", duration=5)

    @patch("scripts.media_validation._frame", return_value=Image.new("RGB", (224, 224)))
    def test_visual_rejection_despite_matching_metadata(self, frame):
        scores = [[.22, .21, .3, .2, .2, .2, .1]] * 3
        with patch.object(SceneMatcher, "_similarities", return_value=scores), self.assertRaisesRegex(ValidationError, "Visual scene mismatch"):
            SceneMatcher().match(Path("unused"), self.spec, self.metadata, duration=5)

    @patch("scripts.media_validation._frame", return_value=Image.new("RGB", (224, 224)))
    def test_positive_raw_score_and_crop_reported(self, frame):
        scores = [[.33, .31, .15, .12, .14, .13, .10]] * 3
        with patch.object(SceneMatcher, "_similarities", side_effect=[scores, [[.21], [.35], [.22]]]):
            result = SceneMatcher().match(Path("unused"), self.spec, self.metadata, duration=5)
        self.assertEqual(result["visual_score"], .33)
        self.assertEqual(result["crop_focus_x"], .5)
        self.assertIn("cannot prove", result["limitations"])

    @patch("scripts.media_validation._frame", return_value=Image.new("RGB", (224, 224)))
    def test_model_unavailable_fails_closed(self, frame):
        with patch.object(SceneMatcher, "_load", side_effect=ValidationError("verifier unavailable")):
            with self.assertRaisesRegex(ValidationError, "unavailable"):
                SceneMatcher().match(Path("unused"), self.spec, self.metadata, duration=5)


@unittest.skipUnless(__import__("shutil").which("ffmpeg") and __import__("shutil").which("ffprobe"), "FFmpeg required")
class QualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        # Synthetic fixtures exclusively for negative and media-tool verification.
        fixtures = {"motion": "testsrc2=size=1920x1080:rate=24",
                    "low": "testsrc2=size=320x180:rate=24",
                    "black": "color=black:size=1920x1080:rate=24"}
        for name, source in fixtures.items():
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", source,
                            "-t", "1.2", "-an", "-c:v", "libx264", "-threads", "1", "-preset", "ultrafast",
                            "-pix_fmt", "yuv420p", str(cls.root / (name + ".mp4"))], check=True, timeout=30)
        # Hold one detailed testsrc frame: detects a static image encoded as video.
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=1920x1080:rate=24",
                        "-vf", "loop=loop=-1:size=1:start=0", "-t", "1.2", "-an", "-c:v", "libx264",
                        "-threads", "1", "-preset", "ultrafast", str(cls.root / "static.mp4")], check=True, timeout=30)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_measured_source_and_crop_scaling(self):
        info = QualityValidator().validate(self.root / "motion.mp4", need=1)
        self.assertEqual((info["width"], info["height"]), (1920, 1080))
        self.assertEqual(info["codec"], "h264")
        self.assertTrue(info["source_full_hd"])
        self.assertFalse(info["source_4k"])
        self.assertGreater(info["portrait_crop_scale"], 1)
        self.assertGreater(info["motion_score"], .65)

    def test_720p_or_lower_never_reported_full_hd(self):
        with self.assertRaisesRegex(ValidationError, "short side"):
            QualityValidator().validate(self.root / "low.mp4")

    def test_black_and_static_rejected(self):
        for name in ("black", "static"):
            with self.subTest(name=name), self.assertRaises(ValidationError):
                QualityValidator().validate(self.root / (name + ".mp4"))

    def test_insufficient_duration_not_looped(self):
        with self.assertRaisesRegex(ValidationError, "without looping"):
            QualityValidator().validate(self.root / "motion.mp4", need=4)

    def test_corrupt_file_rejected(self):
        corrupt = self.root / "corrupt.mp4"
        corrupt.write_bytes(b"not a movie")
        with self.assertRaisesRegex(ValidationError, "ffprobe"):
            QualityValidator().validate(corrupt)


if __name__ == "__main__":
    unittest.main()
