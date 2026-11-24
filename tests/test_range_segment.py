"""Offline proof of HTTP range extraction without contacting a stock provider."""
import os
import re
import subprocess
import tempfile
import unittest
import urllib.request
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from threading import Thread
from media_validation import VideoDownloader,ValidationError,QualityValidator
from range_segment import extract_segment

class RangeTests(unittest.TestCase):
    def test_extract_only_needed_frames(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            source=root/"source.mp4"
            subprocess.run(["ffmpeg","-y","-v","error","-f","lavfi","-i",
                "testsrc2=size=1280x720:rate=25","-t","24","-c:v","libx264",
                "-threads","2","-preset","ultrafast","-crf","16",
                "-movflags","+faststart",str(source)],check=True,timeout=90)
            total=source.stat().st_size
            class Origin(BaseHTTPRequestHandler):
                def log_message(self,*args): pass
                def do_GET(self):
                    m=re.fullmatch(r"bytes=(\d+)-(\d*)",self.headers.get("Range",""))
                    if not m:
                        self.send_error(400);return
                    a=int(m[1]);b=min(total-1,int(m[2])) if m[2] else total-1
                    self.send_response(206)
                    self.send_header("Content-Range",f"bytes {a}-{b}/{total}")
                    self.send_header("Content-Length",str(b-a+1))
                    self.end_headers()
                    try:
                        with source.open("rb") as f:
                            f.seek(a);left=b-a+1
                            while left:
                                d=f.read(min(left,65536))
                                if not d: break
                                self.wfile.write(d);left-=len(d)
                    except OSError: pass
            server=ThreadingHTTPServer(("127.0.0.1",0),Origin)
            t=Thread(target=server.serve_forever,daemon=True);t.start()
            try:
                dl=VideoDownloader(cache_dir=root/"cache",max_bytes=64*1024**2,
                                   max_cache_bytes=128*1024**2,min_free_bytes=0,total_timeout=60)
                # Test-only local origin, production validates public HTTPS.
                dl.validate_url=lambda url: None
                dest,proof=extract_segment(f"http://127.0.0.1:{server.server_port}/video",dl,3)
                self.assertLess(proof["transferred_bytes"],total)
                self.assertEqual(proof["source_bytes"],total)
                q=QualityValidator().validate(dest)
                self.assertGreaterEqual(q["duration"],2.8)
                self.assertLess(q["duration"],4)
                self.assertEqual(q["height"],720)
                later,proof2=extract_segment(f"http://127.0.0.1:{server.server_port}/video",dl,3,offset=12)
                self.assertEqual(proof2["source_offset_seconds"],12)
                self.assertLess(proof2["transferred_bytes"],total)
                self.assertNotEqual(later,dest)
                q2=QualityValidator().validate(later)
                self.assertGreaterEqual(q2["duration"],2.8)
                self.assertLess(q2["duration"],4)
                self.assertEqual(q2["height"],720)
            finally:
                server.shutdown();server.server_close();t.join(timeout=2)

if __name__=="__main__": unittest.main()
