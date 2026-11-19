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
    expected = tuple(int(v) for v in os.environ.get('RESOLUTION', '720x1280').lower().split('x'))
    if len(expected) != 2 or min(expected) < 720:
        raise RuntimeError('RESOLUTION must specify width x height, minimum dimension 720')
    if (info['width'], info['height']) != expected:
        raise RuntimeError(f'Output resolution mismatch: expected {expected}, got {(info["width"], info["height"])}')
    if not info.get('has_audio'):
        # FFprobe explicitly checks audio; never infer it from a filename.
        import subprocess
        data = json.loads(subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(video)],
                                        capture_output=True, text=True, check=True, timeout=30).stdout)
        if not any(x.get('codec_type') == 'audio' for x in data.get('streams', [])):
            raise RuntimeError('MP4 has no narration audio stream')
    voice = str(metadata.get('voice', ''))
    # A rendered MP4 with old Piper Joe must not pass a STRICT English
    # workflow, even if the caller bypasses the early voice preflight.
    from english_reference_policy import (
        enforce_english_reference_only, REFERENCE_VOICE_ID,
        ENGLISH_REFERENCE_SHA256, ENGLISH_REFERENCE_OPUS_SHA256)
    language = str(metadata.get('language') or os.environ.get('LANGUAGE', 'en'))
    if language == 'en':
        # No output can ever pass with Piper Joe/Edge/LJSpeech or a fake voice.
        if voice != 'reference:' + REFERENCE_VOICE_ID:
            raise RuntimeError('Narrator identity mismatch: approved English reference was not used')
        enforce_english_reference_only(language)
        if voice_report is None or not voice_report.is_file():
            raise RuntimeError('Approved reference voice verification report missing')
        reference_proof = json.loads(voice_report.read_text(encoding='utf-8'))
        provenance = reference_proof.get('provenance', {})
        if (reference_proof.get('state') != 'ready'
                or reference_proof.get('engine') != 'reference'
                or reference_proof.get('voice') != REFERENCE_VOICE_ID
                or reference_proof.get('timing') != 'aligned'
                or provenance.get('reference_original_sha256') != ENGLISH_REFERENCE_SHA256
                or provenance.get('reference_opus_sha256') != ENGLISH_REFERENCE_OPUS_SHA256
                or provenance.get('voice') != REFERENCE_VOICE_ID
                or provenance.get('reference_private') is not True
                or provenance.get('alignment') !=
                    'faster-whisper-base.en actual generated WAV word timestamps'
                or float(provenance.get('speaker_similarity_cosine', 0)) < .70):
            raise RuntimeError('Approved English reference speaker or real caption alignment not verified')
    elif language == 'de':
        if os.getenv('PURFFLE_NARRATOR_LOCK', '0') == '1' and voice != 'piper:de_DE-thorsten-medium':
            raise RuntimeError('Narrator identity mismatch: locked German Thorsten was not used')
    else:
        raise RuntimeError('Unsupported narrator language')
    if not voice.startswith(('reference:', 'edge:', 'piper:')) or metadata.get('timing') not in ('native', 'aligned'):
        raise RuntimeError('Narration does not have verified native/aligned timing')
    if voice.startswith('piper:'):
        if voice_report is None or not voice_report.is_file():
            raise RuntimeError('Local voice alignment/license report missing')
        proof = json.loads(voice_report.read_text(encoding='utf-8'))
        provenance = proof.get('provenance', {})
        approved = {'de_DE-thorsten-medium': 'CC0-1.0'}
        model = voice.partition(':')[2]
        from local_voice import provenance as expected_provenance
        if language != 'de':
            raise RuntimeError('All generic English Piper voices have been removed')
        lang = 'de'
        expected = expected_provenance(lang)
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
    scenes = report.get('scenes') or []
    if (not scenes or any(scene.get('status') != 'selected' for scene in scenes)
            or [scene.get('index') for scene in scenes] != list(range(1, len(scenes) + 1))):
        raise RuntimeError('Not every scene has verified moving footage: final scene reports are missing or inconsistent')
    if any(not scene.get('source') or not scene.get('sha256')
           or not scene.get('match') or not scene.get('license') for scene in scenes):
        raise RuntimeError('Footage provenance or frame verification missing in scene report')
    # Exactly the same bound is checked during candidate selection and
    # FFmpeg segment preparation. Scene reports retain the measured resize.
    from media_validation import portrait_crop_allowed
    if any(not portrait_crop_allowed(
            scene.get('quality', {}).get('portrait_crop_scale', float('inf')))
            for scene in scenes):
        raise RuntimeError('insufficient_native_resolution: portrait crop upscale exceeds quality limit')
    if len({scene['sha256'] for scene in scenes}) != len(scenes):
        raise RuntimeError('Duplicate footage repeated across scenes')
    return info, report


def main():
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    target = Path(os.environ['JOB_RESULT'])
    result = {'status': 'failed', 'mp4': None}
    stage = 'setup'
    try:
        # Avoid expensive footage/model work when the only approved English
        # speaker has not been validated for this runner. Never use Joe as a
        # substitute merely to make the video job appear successful.
        stage = 'voice_identity_preflight'
        from english_reference_policy import enforce_english_reference_only
        enforce_english_reference_only(os.environ.get('LANGUAGE', 'en'))
        stage = 'setup'
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
                    resolution=tuple(int(v) for v in os.environ.get('RESOLUTION', '720x1280').lower().split('x')), fps=30, max_shot_seconds=0, transition='none',
                    background_video='', music_volume=0, sound_effects=False,
                    caption_emoji=False, color_grade='none', ken_burns=False,
                    end_cta='', watermark='none', hook_overlay=False,  # Keep title area blank in every Short; preserve word captions.
                    upload=False, also_languages=[], localize_metadata=[], notify_webhook='',
                    workers=1, crf=18, preset='medium', target_seconds=24)  # Bootstrap only; topic-adaptive duration set after footage/evidence
        stage = 'production'
        studio = Studio(s)
        if os.environ.get('PURFFLE_MEDIA_FIRST', '1') == '1':
            from media_first import (prepare_verified_palette, use_palette,
                                     validate_narration_timing)
            stage = 'media_preflight'
            palette = prepare_verified_palette(
                os.environ['VIDEO_TOPIC'], s, studio.llm,
                min_scenes=3, max_scenes=4, clip_seconds=10.0)
            from science_sources import discover_evidence, screen_narration, use_evidence
            stage = 'science_sources'
            try:
                evidence = discover_evidence(os.environ['VIDEO_TOPIC'], s.language)
            except RuntimeError as source_error:
                from science_sources import write_source_failure
                write_source_failure(str(source_error),
                                     os.environ.get('SCIENCE_REPORT', 'science-report.json'))
                raise
            from retention_storyboard import choose_duration_seconds
            fact_count = len(getattr(evidence, 'sources', []) or [])
            planned_seconds = choose_duration_seconds(
                os.environ['VIDEO_TOPIC'], len(palette.items),
                fact_count=fact_count)
            palette.planned_seconds = planned_seconds
            s = replace(s, target_seconds=planned_seconds)
            studio.s = s
            studio.clock.scale = max(.25, planned_seconds / 40)
            logging.info('Adaptive Shorts target: %d seconds from %d verified scenes and %d evidence sources',
                         planned_seconds, len(palette.items), fact_count)
            stage = 'grounded_script'
            for attempt in range(2):
                with use_palette(palette), use_evidence(evidence):
                    screenplay, pick, writer = studio.draft(
                        os.environ['VIDEO_TOPIC'], style='facts')
                try:
                    from science_fact_guard import validate_unsourced_quantities
                    validate_unsourced_quantities(
                        screenplay, os.environ['VIDEO_TOPIC'])
                    validate_narration_timing(palette, screenplay, s.language)
                    stage = 'retention_review'
                    from retention_storyboard import audit_storyboard
                    storyboard_audit = audit_storyboard(
                        os.environ['VIDEO_TOPIC'], screenplay, s.language,
                        planned_seconds=planned_seconds)
                    stage = 'science_review'
                    screen_narration(
                        screenplay, evidence, studio.llm,
                        path=os.environ.get('SCIENCE_REPORT', 'science-report.json'))
                    from retention_storyboard import save_storyboard_report
                    save_storyboard_report(
                        os.environ.get('RETENTION_REPORT',
                                       str(target.with_name('retention-report.json'))),
                        storyboard_audit)
                    break
                except RuntimeError as script_error:
                    if attempt:
                        raise
                    logging.warning(
                        'V3 factuality, source or timing preflight rejected draft (%s); '
                        'requesting one more source-grounded script',
                        str(script_error)[:200])
                    stage = 'grounded_script'
            stage = 'production'
            # The footage has already been downloaded, visually checked and
            # deduplicated. Do not ask the providers to search again after TTS.
            made = studio.produce(screenplay, pick, writer, upload=False,
                                  media_map=palette.media_map,
                                  credits=palette.credits)
        else:
            made = studio.make(os.environ['VIDEO_TOPIC'], upload=False)
        if not made.ok or not made.video:
            raise RuntimeError(made.error or made.status or 'Upstream production failed')
        video = Path(made.video)
        folder = video.parent
        metadata = json.loads((folder / 'metadata.json').read_text(encoding='utf-8'))
        voice_report = Path(os.environ['VOICE_REPORT'])
        stage = 'output_validation'
        info, footage = validate_result(video, metadata, folder / 'captions.srt', Path(os.environ['FOOTAGE_REPORT']), voice_report)
        if os.environ.get('PURFFLE_MEDIA_FIRST', '1') == '1':
            stage = 'final_opening_qa'
            if footage.get('opening_review', {}).get('state') != 'selected':
                raise RuntimeError('opening_quality_unverified: real opening selection proof missing')
            from shorts_final_qa import audit_rendered_opening
            final_opening = audit_rendered_opening(video)
            from retention_storyboard import save_storyboard_report
            save_storyboard_report(
                os.environ.get('RETENTION_REPORT',
                               str(target.with_name('retention-report.json'))),
                {**storyboard_audit, 'final_opening_qa': final_opening,
                 'verified_source_opening': footage['opening_review']},
                duration_seconds=info['duration'])
            stage = 'output_validation'
        result.update(status='ok', stage='complete', mp4=str(video), output_probe=info,
                      footage_report=os.environ['FOOTAGE_REPORT'],
                      metadata=str(folder / 'metadata.json'), captions=str(folder / 'captions.srt'),
                      voice=metadata['voice'], caption_timing=metadata['timing'],
                      voice_report=str(voice_report),
                      retention_report=os.environ.get(
                          'RETENTION_REPORT', str(target.with_name('retention-report.json')))
                          if os.environ.get('PURFFLE_MEDIA_FIRST', '1') == '1' else None,
                      science_report=os.environ.get('SCIENCE_REPORT', 'science-report.json'),
                      science_screening=evidence.method if os.environ.get('PURFFLE_MEDIA_FIRST', '1') == '1' else 'legacy_unreviewed',
                      test_result='validated_output', sources=sorted({x['source'] for x in footage['scenes']}))
    except Exception as exc:
        logging.exception('Video production failed')
        result.update(error=str(exc), exception_type=type(exc).__name__, stage=stage)
    finally:
        write_json(target, result)
    return 0 if result['status'] == 'ok' else 1


if __name__ == '__main__':
    raise SystemExit(main())
