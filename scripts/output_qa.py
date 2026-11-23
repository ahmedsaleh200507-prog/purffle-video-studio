"""Full-timeline technical QC, shared by Shorts and documentaries."""
import json
import math
from pathlib import Path
import re
import subprocess


def caption_intervals(path, duration):
    text = Path(path).read_text(encoding='utf8')
    rows = re.findall(r'(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})', text)
    def seconds(s):
        h, m, tail = s.split(':'); sec, ms = tail.split(',')
        return int(h)*3600 + int(m)*60 + int(sec) + int(ms)/1000
    intervals = [(seconds(a), seconds(b)) for a, b in rows]
    if not intervals or any(a < 0 or b <= a or b > duration + .25 for a, b in intervals):
        raise RuntimeError('output_qa_invalid_caption_timing')
    if any(b[0] < a[1] - .08 for a, b in zip(intervals, intervals[1:])):
        raise RuntimeError('output_qa_overlapping_captions')
    if intervals[0][0] > 1.5 or duration - intervals[-1][1] > 2.5:
        raise RuntimeError('output_qa_caption_coverage_incomplete')
    return intervals


def validate_timeline(path, captions, *, expected_size, expected_duration=None, expected_text=None):
    path = Path(path)
    if not path.is_file() or path.stat().st_size < 1024:
        raise RuntimeError('output_qa_mp4_missing_or_empty')
    p = subprocess.run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)],
                       capture_output=True, text=True, timeout=30, check=True)
    data = json.loads(p.stdout)
    v = next((s for s in data.get('streams',[]) if s.get('codec_type')=='video'), {})
    a = next((s for s in data.get('streams',[]) if s.get('codec_type')=='audio'), {})
    duration = float(data.get('format',{}).get('duration',0))
    numerator, denominator = v.get('avg_frame_rate','0/1').split('/')
    fps = float(numerator)/max(1, float(denominator))
    if (not a or (v.get('width'),v.get('height')) != tuple(expected_size)
            or abs(fps-30) > .05 or not math.isfinite(duration) or duration <= 0):
        raise RuntimeError('output_qa_invalid_resolution_fps_audio_or_duration')
    if expected_duration is not None and abs(duration-float(expected_duration)) > max(.5, duration*.01):
        raise RuntimeError('output_qa_narration_duration_mismatch')
    # Detect across the WHOLE output with downscaled video and mono audio;
    # no HD frame buffers or PCM recording need to be retained in Python.
    p = subprocess.run(['ffmpeg','-hide_banner','-nostdin','-v','info','-threads','2',
        '-filter_threads','1','-i',str(path),'-vf','scale=160:-2,blackdetect=d=0.45:pix_th=0.05:pic_th=0.98',
        '-af','silencedetect=noise=-45dB:d=2.5','-f','null','-'],
        capture_output=True,text=True,timeout=max(60,min(480,duration*1.5)),check=True)
    blacks = re.findall(r'black_start:([\d.]+) black_end:([\d.]+)',p.stderr)
    silences = re.findall(r'silence_end: ([\d.]+) \| silence_duration: ([\d.]+)',p.stderr)
    if blacks:
        raise RuntimeError('output_qa_black_or_empty_scene: '+str(blacks[:4]))
    if silences or re.search(r'silence_start:',p.stderr):
        raise RuntimeError('output_qa_long_silence_detected')
    intervals = caption_intervals(captions,duration)
    if expected_text is not None:
        blocks = re.split(r'\n\s*\n', Path(captions).read_text(encoding='utf8').strip())
        actual = ' '.join(' '.join(block.splitlines()[2:]) for block in blocks)
        def tokens(text):
            return re.findall(r"\w+", re.sub(r'<[^>]*>', '', text).casefold())
        if tokens(actual) != tokens(expected_text):
            raise RuntimeError('output_qa_caption_transcript_incomplete_or_changed')
    return {'state':'passed','duration':duration,'fps':fps,'caption_cues':len(intervals),
            'full_decode':True,'black_intervals':[],'silence_over_2_5s':[],
            'limits':'Timing/coverage and PCM energy, not speech recognition or factual verification'}
