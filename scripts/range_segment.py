"""Bounded HTTP byte-range extraction through a private loopback bridge.

The upstream server must return valid 206 responses. FFmpeg never receives
the upstream URL, credentials, redirects, or arbitrary proxy destinations.
Only a single licensed asset is served. No restriction bypass.
"""
import hashlib
import math
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from media_validation import ValidationError

CONTENT_RANGE = re.compile(r"bytes (\d+)-(\d+)/(\d+)", re.I)
REQUEST_RANGE = re.compile(r"bytes=(\d+)-(\d*)", re.I)


class RangeAsset:
    def __init__(self, url, downloader, *, budget, seconds):
        self.url = url
        self.downloader = downloader
        self.budget = int(budget)
        self.deadline = time.monotonic() + seconds
        self.lock = threading.Lock()
        self.transferred = 0
        self.requests = 0
        self.total = None

    def remaining_time(self):
        left = self.deadline-time.monotonic()
        if left <= 0:
            raise ValidationError("Partial download time budget exceeded")
        return min(self.downloader.timeout, left)

    def open_range(self, start, end=None):
        current = self.url
        with self.lock:
            self.requests += 1
            if self.requests > 32 or self.transferred >= self.budget:
                raise ValidationError("Partial download request or byte budget exhausted")
        for _ in range(6):
            self.downloader.validate_url(current)
            # Same public HTTPS URL and redirect checks as the full downloader.
            parts = urllib.parse.urlsplit(current)
            current = urllib.parse.urlunsplit((parts.scheme,parts.netloc,
                urllib.parse.quote(parts.path,safe="/%:@!$&'()*+,;=-._~"),
                urllib.parse.quote(parts.query,safe="=&%/?+,:;@!$'()*~-._"),""))
            req = urllib.request.Request(current,headers={
                "User-Agent":"PurffleVideoStudio/2.0 (+https://github.com/ahmedsaleh200507-prog/purffle-video-studio)",
                "Range":f"bytes={start}-{'' if end is None else end}",
                "Accept-Encoding":"identity",
                "Accept":"video/*,application/octet-stream;q=0.8"})
            try:
                response = self.downloader.opener.open(req,timeout=self.remaining_time())
            except urllib.error.HTTPError as exc:
                if exc.code in (301,302,303,307,308):
                    location=exc.headers.get("Location")
                    exc.close()
                    if not location:
                        raise ValidationError("Partial download redirect without location")
                    current=urllib.parse.urljoin(current,location)
                    continue
                exc.close()
                raise ValidationError(f"Partial download HTTP {exc.code}") from None
            try:
                self.downloader.validate_url(response.geturl())
                match=CONTENT_RANGE.fullmatch(response.headers.get("Content-Range","").strip())
                if response.getcode()!=206 or not match:
                    raise ValidationError("Source does not support verified HTTP byte ranges")
                first,last,total=map(int,match.groups())
                if (first!=start or last<first or total<=last or
                        (end is not None and last> end) or
                        (self.total is not None and self.total!=total)):
                    raise ValidationError("Invalid or changing upstream byte range")
                content_type=response.headers.get("Content-Type","").split(";",1)[0].lower()
                if content_type.startswith(("text/","image/")) or content_type in ("application/json","application/xml"):
                    raise ValidationError("Partial response is not video")
                if response.headers.get("Content-Encoding","identity").lower() not in ("","identity"):
                    raise ValidationError("Compressed range response unsupported")
                self.total=total
                return response,first,last
            except BaseException:
                response.close()
                raise
        raise ValidationError("Too many partial download redirects")

    def read(self,response,count):
        self.remaining_time()
        # Serialize byte accounting and reads so concurrent requests cannot
        # overrun the shared transfer cap. No unbounded buffering.
        with self.lock:
            allowed=min(count,65536,self.budget-self.transferred)
            if allowed<=0:
                raise ValidationError("Partial download byte budget exhausted")
            data=response.read(allowed)
            self.transferred+=len(data)
            return data

    def probe(self):
        response,first,last=self.open_range(0,0)
        with response:
            if first!=0 or last!=0 or len(self.read(response,1))!=1:
                raise ValidationError("HTTP range probe failed")


def handler_for(asset):
    class Handler(BaseHTTPRequestHandler):
        protocol_version="HTTP/1.0"

        def log_message(self,*args):
            pass

        def do_HEAD(self):
            if self.path!="/asset":
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Length",str(asset.total))
            self.send_header("Accept-Ranges","bytes")
            self.send_header("Content-Type","application/octet-stream")
            self.end_headers()

        def do_GET(self):
            if self.path!="/asset":
                self.send_error(404)
                return
            match=REQUEST_RANGE.fullmatch(self.headers.get("Range","bytes=0-"))
            if not match:
                self.send_error(416)
                return
            start=int(match[1])
            end=int(match[2]) if match[2] else None
            if start>=asset.total or (end is not None and end<start):
                self.send_error(416)
                return
            try:
                response,first,last=asset.open_range(start,end)
            except Exception:
                self.send_error(502)
                return
            try:
                with response:
                    self.send_response(206)
                    self.send_header("Content-Range",f"bytes {first}-{last}/{asset.total}")
                    self.send_header("Content-Length",str(last-first+1))
                    self.send_header("Accept-Ranges","bytes")
                    self.send_header("Content-Type","application/octet-stream")
                    self.end_headers()
                    remaining=last-first+1
                    while remaining:
                        data=asset.read(response,remaining)
                        if not data:
                            break
                        self.wfile.write(data)
                        remaining-=len(data)
            except (OSError,ValidationError):
                # FFmpeg normally closes its range request after enough packets.
                pass
            finally:
                self.close_connection=True
    return Handler


def extract_segment(url, downloader, seconds):
    """Extract opening interval; retain source resolution and actual timestamps.

    Byte count is bounded, not guaranteed to equal exactly the desired
    playback duration: MP4 indexes and GOP/keyframe data can add overhead.
    """
    seconds=float(seconds)
    if not math.isfinite(seconds) or not 0.6<=seconds<=90:
        raise ValidationError("Invalid partial clip duration")
    budget=min(downloader.max_bytes,64*1024*1024)
    timeout=min(downloader.total_timeout,85)
    folder=Path(downloader.cache_dir)
    folder.mkdir(parents=True,exist_ok=True)
    if (shutil.disk_usage(folder).free < downloader.min_free_bytes+budget or
        sum(p.stat().st_size for p in folder.iterdir() if p.is_file())+budget>downloader.max_cache_bytes):
        raise ValidationError("Insufficient cache or disk for partial download")
    asset=RangeAsset(url,downloader,budget=budget,seconds=timeout)
    asset.probe()
    server=ThreadingHTTPServer(("127.0.0.1",0),handler_for(asset))
    server.daemon_threads=True
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    fd,name=tempfile.mkstemp(dir=folder,suffix=".partial.mp4")
    os.close(fd)
    temp=Path(name)
    thread.start()
    try:
        local=f"http://127.0.0.1:{server.server_port}/asset"
        # Only ordinary MP4/MOV (and WebM/Matroska) demuxers; do not enable
        # external MOV data references, playlists, concat or arbitrary URLs.
        env={k:v for k,v in os.environ.items() if k.lower() not in
             ("http_proxy","https_proxy","all_proxy","no_proxy")}
        env["NO_PROXY"]="127.0.0.1,localhost"
        result=subprocess.run(["ffmpeg","-hide_banner","-nostdin","-y","-loglevel","error",
            "-protocol_whitelist","http,tcp","-format_whitelist","mov,matroska,webm",
            "-rw_timeout","10000000","-probesize","4194304","-analyzeduration","4000000",
            "-i",local,"-map","0:v:0","-an","-sn","-dn","-t",f"{seconds:.3f}",
            "-c:v","copy","-fs",str(budget),"-movflags","+faststart",str(temp)],
            capture_output=True,timeout=max(1,asset.deadline-time.monotonic()),env=env)
        if result.returncode or temp.stat().st_size<1024:
            raise ValidationError("Range extraction failed: unsupported container or insufficient range data")
        # ffmpeg may emit a short file when input is truncated. The shared
        # validator checks measured duration before any acceptance.
        key=hashlib.sha256((url+"|opening|"+str(seconds)).encode()).hexdigest()
        target=folder/(key+".segment.mp4")
        temp.replace(target)
        evidence={"mode":"http_range","source_offset_seconds":0.0,
                  "requested_seconds":seconds,"transferred_bytes":asset.transferred,
                  "source_bytes":asset.total,"byte_budget":budget}
        print("[PARTIAL VIDEO]",evidence,flush=True)
        return target,evidence
    except subprocess.TimeoutExpired:
        raise ValidationError("Partial video extraction timed out") from None
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        temp.unlink(missing_ok=True)
