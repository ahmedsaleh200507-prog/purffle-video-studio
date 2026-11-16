"""One isolated, free-provider-only upstream production job with exact output validation."""
from __future__ import annotations

import json
import logging
import os
from dataclasses import replace
from pathlib import Path

from batch import write_json


def validate_result(video: Path, metadata: dict, captions: Path, footage_report: Path, voice_report: Path | None = None):
    from media_validation import QualityValidator
    info = QualityValidator().validate(video)
    if (info['width'], info['height']) != (1080, 1920):
        raise RuntimeError('Output is not 1080x1920')
    if not info.get('has_audio'):
        # FFprobe explicitly checks audio; never infer it from a filename.
        import subprocess
        data = json.loads(subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(video)],
                                        capture_output=True, text=True, check=True, timeout=30).stdout)
        if not any(x.get('codec_type') == 'audio' for x in data.get('streams', [])):
            raise RuntimeError('MP4 has no narration audio stream')
    voice = str(metadata.get('voice', ''))
    if not voice.startswith(('edge:', 'piper:')) or metadata.get('timing') not in ('native', 'aligned'):
        raise RuntimeError('Narration does not have verified native/aligned timing')
    if voice.startswith('piper:'):
        if voice_report is None or not voice_report.is_file():
            raise RuntimeError('Local voice alignment/license report missing')
        proof = json.loads(voice_report.read_text(encoding='utf-8'))
        provenance = proof.get('provenance', {})
        approved = {'en_US-ljspeech-high': 'Public-Domain', 'de_DE-thorsten-medium': 'CC0-1.0'}
        model = voice.partition(':')[2]
        from local_voice import provenance as expected_provenance
        expected = expected_provenance('en' if model == 'en_US-ljspeech-high' else 'de')
        if (model not in approved or proof.get('state') != 'ready' or proof.get('engine') != 'piper'
                or proof.get('voice') != model or proof.get('timing') != 'aligned'
                or provenance.get('alignment') != 'native_phoneme_samples'
                or provenance.get('model') != model
                or provenance.get('license', {}).get('id') != approved[model]
                or any(provenance.get(k) != expected[k] for k in ('model_sha256', 'model_revision', 'model_url'))
                or provenance.get('license', {}).get('url') != expected['license']['url']):
            raise RuntimeError('Local voice alignment/license provenance invalid')
    if not captions.is_file() or '-->' not in captions.read_text(encoding='utf-8'):
        raise RuntimeError('Synchronized captions missing')
    report = json.loads(footage_report.read_text(encoding='utf-8'))
    if not report.get('scenes') or any(x.get('status') != 'selected' for x in report['scenes']):
        raise RuntimeError('Not every scene has verified moving footage')
    return info, report


def main():
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    target = Path(os.environ['JOB_RESULT'])
    result = {'status': 'failed', 'mp4': None}
    try:
        from studio_runtime import install
        install()
        from purffle_shorts.config import Settings
        from purffle_shorts.pipeline import Studio
        if not os.environ.get('GROQ_API_KEY'):
            raise RuntimeError('GROQ_API_KEY missing from GitHub Actions Secrets')
        s = replace(Settings.from_env(), language=os.environ['LANGUAGE'],
                    llm_provider='groq', llm_model='openai/gpt-oss-20b', llm_fallbacks=[],
                    openai_api_key='', llm_api_key='',
                    tts_engine='edge', offline=False, script_review='off', seo_keywords=False,
                    resolution=(1080, 1920), fps=30, max_shot_seconds=0, transition='none',
                    background_video='', music_volume=0, sound_effects=False,
                    caption_emoji=False, color_grade='none', ken_burns=False,
                    upload=False, also_languages=[], localize_metadata=[], notify_webhook='',
                    workers=1, crf=18, preset='medium', target_seconds=25)
        made = Studio(s).make(os.environ['VIDEO_TOPIC'], upload=False)
        if not made.ok or not made.video:
            raise RuntimeError(made.error or made.status or 'Upstream production failed')
        video = Path(made.video)
        folder = video.parent
        metadata = json.loads((folder / 'metadata.json').read_text(encoding='utf-8'))
        voice_report = Path(os.environ['VOICE_REPORT'])
        info, footage = validate_result(video, metadata, folder / 'captions.srt', Path(os.environ['FOOTAGE_REPORT']), voice_report)
        result.update(status='ok', mp4=str(video), output_probe=info,
                      footage_report=os.environ['FOOTAGE_REPORT'],
                      metadata=str(folder / 'metadata.json'), captions=str(folder / 'captions.srt'),
                      voice=metadata['voice'], caption_timing=metadata['timing'],
                      voice_report=str(voice_report),
                      test_result='validated_output', sources=sorted({x['source'] for x in footage['scenes']}))
    except Exception as exc:
        logging.exception('Video production failed')
        result.update(error=str(exc))
    finally:
        write_json(target, result)
    return 0 if result['status'] == 'ok' else 1


if __name__ == '__main__':
    raise SystemExit(main())
