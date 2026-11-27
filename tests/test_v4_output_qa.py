"""Real FFmpeg files below are synthetic test fixtures, never stock production."""
from pathlib import Path
import shutil
import subprocess
import pytest
from output_qa import validate_timeline, caption_intervals

pytestmark=pytest.mark.skipif(not shutil.which('ffmpeg'),reason='FFmpeg required')


def render(tmp_path, vf='testsrc2=size=160x284:rate=30', audio='sine=frequency=350:sample_rate=16000', tail=None):
    target=tmp_path/'test.mp4'
    args=['ffmpeg','-nostdin','-v','error','-y','-f','lavfi','-i',vf,'-f','lavfi','-i',audio,
          '-t','3','-c:v','libx264','-threads','1','-pix_fmt','yuv420p','-c:a','aac']
    if tail: args += tail
    subprocess.run(args+[str(target)],check=True,capture_output=True,timeout=25)
    caption=tmp_path/'captions.srt'
    caption.write_text('1\n00:00:00,000 --> 00:00:02,900\nTest fixture.\n')
    return target,caption


def test_real_full_decode_and_captions(tmp_path):
    video,captions=render(tmp_path)
    qa=validate_timeline(video,captions,expected_size=(160,284),expected_duration=3)
    assert qa['state']=='passed' and qa['full_decode']


@pytest.mark.parametrize('kind',['black','silence','badfps','truncated'])
def test_real_bad_mp4_never_success(tmp_path,kind):
    video,captions=render(tmp_path,vf='color=black:size=160x284:rate=30' if kind=='black' else 'testsrc2=size=160x284:rate=30',
                          audio='anullsrc=r=16000:cl=mono' if kind=='silence' else 'sine=frequency=350:sample_rate=16000',
                          tail=['-r','24'] if kind=='badfps' else None)
    if kind=='truncated': video.write_bytes(video.read_bytes()[:100])
    with pytest.raises((RuntimeError,subprocess.CalledProcessError)):
        validate_timeline(video,captions,expected_size=(160,284))


def test_caption_tail_and_out_of_order_fail(tmp_path):
    srt=tmp_path/'bad.srt';srt.write_text('1\n00:00:02,000 --> 00:00:05,000\nLate\n')
    with pytest.raises(RuntimeError): caption_intervals(srt,3)


def test_complete_caption_timing_cannot_hide_missing_sentence(tmp_path):
    video,captions=render(tmp_path)
    with pytest.raises(RuntimeError,match='caption_transcript'):
        validate_timeline(video,captions,expected_size=(160,284),expected_text='Test fixture. Missing sentence.')
    with pytest.raises(RuntimeError,match='narration_duration'):
        validate_timeline(video,captions,expected_size=(160,284),expected_duration=8)

def test_caption_internal_gap_rejected(tmp_path):
    srt=tmp_path/'gap.srt'
    srt.write_text('1\n00:00:00,000 --> 00:00:01,000\nFirst\n\n2\n00:00:06,000 --> 00:00:07,000\nLast\n')
    with pytest.raises(RuntimeError,match='internal_caption_gap'):
        caption_intervals(srt,7)

def test_audio_stream_ending_early_is_rejected(tmp_path):
    video,captions=render(tmp_path,audio='sine=frequency=350:sample_rate=16000:duration=1')
    with pytest.raises(RuntimeError,match='audio_video_timeline_mismatch'):
        validate_timeline(video,captions,expected_size=(160,284))
