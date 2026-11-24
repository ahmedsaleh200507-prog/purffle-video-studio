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
    language = str(metadata.get('language') or os.environ.get('LANGUAGE', 'en'))
    expected_voice = {'en': 'en_US-joe-medium', 'de': 'de_DE-thorsten-medium'}.get(language)
    if expected_voice is None or voice != 'piper:' + expected_voice:
        raise RuntimeError('Narrator identity mismatch: fixed Piper Joe/Thorsten required')
    if metadata.get('timing') != 'aligned':
        raise RuntimeError('Narration lacks native sample alignment')
    if voice.startswith('piper:'):
        if voice_report is None or not voice_report.is_file():
            raise RuntimeError('Local voice alignment/license report missing')
        proof = json.loads(voice_report.read_text(encoding='utf-8'))
        provenance = proof.get('provenance', {})
        approved = {'en_US-joe-medium': 'CC0', 'de_DE-thorsten-medium': 'CC0-1.0'}
        model = voice.partition(':')[2]
        from local_voice import provenance as expected_provenance
        lang = language
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
    # The proof must survive beyond candidate selection: for v4, every MP4
    # scene must retain a reviewed spoken-scene contract AND a passed actual
    # portrait multi-timestamp CLIP event check. Never mark a playable MP4
    # "successful" merely because generic topic stock was downloaded.
    if report.get('strategy') == 'v4_evidence_first_director_verified_before_voice':
        if any(
            not scene.get('director_contract')
            or scene.get('match', {}).get('director_check', {}).get('verified') is not True
            for scene in scenes
        ):
            raise RuntimeError(
                'visual_director_unverified: at least one narrated scene '
                'lacks an independently checked real-video action match')
        if [scene.get('director_contract', {}).get('index') for scene in scenes] != list(
                range(1, len(scenes) + 1)):
            raise RuntimeError(
                'visual_director_sequence_mismatch: spoken scene and verified clip order differ')
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
        # Validate language before setup; pinned Piper model identity and
        # native alignment are checked during synthesis and final acceptance.
        stage = 'voice_identity_preflight'
        from english_reference_policy import enforce_english_reference_only
        enforce_english_reference_only(os.environ.get('LANGUAGE', 'en'))
        stage = 'setup'
        from studio_runtime import install
        install()
        from purffle_shorts.config import Settings
        from purffle_shorts.pipeline import Studio
        groq_ready = bool(os.environ.get('GROQ_API_KEY'))
        gemini_ready = bool(os.environ.get('GEMINI_API_KEY'))
        from local_llm import enabled as local_enabled, MODEL as local_model
        local_ready=local_enabled()
        if not (groq_ready or gemini_ready or local_ready):
            raise RuntimeError('No configured text provider')
        # Existing approved narrator, scientific source screening and actual
        # video quality checks remain unchanged. This selects TEXT only.
        # Gemini 3.1 Flash-Lite has a higher request allowance on the
        # user's configured free project. Reserve Groq as a live secondary.
        # The pinned upstream retries the same JSON schema with the fallback.
        main_llm = 'gemini' if gemini_ready else ('groq' if groq_ready else 'purffle-local')
        selected_model = ('gemini-3.1-flash-lite' if gemini_ready
                          else 'openai/gpt-oss-20b' if groq_ready else local_model)
        fallbacks = ['groq'] if gemini_ready and groq_ready else []
        if local_ready and main_llm!='purffle-local':
            fallbacks.append('purffle-local')
        from cloud_model_router import enabled as router_enabled, MODELS
        if router_enabled():
            main_llm='purffle-router'
            selected_model=MODELS[0][1]
            fallbacks=[]
            print("[SHORTS LLM] Shared six-cloud/two-local model router",flush=True)
        else:
            print(f"[SHORTS LLM] primary={main_llm} fallback={fallbacks}",flush=True)
        s = replace(Settings.from_env(), language=os.environ['LANGUAGE'],
                    llm_provider=main_llm, llm_model=selected_model,
                    llm_fallbacks=fallbacks,
                    openai_api_key='', llm_api_key='',
                    tts_engine='piper', offline=False, script_review='off', seo_keywords=False,
                    resolution=tuple(int(v) for v in os.environ.get('RESOLUTION', '720x1280').lower().split('x')), fps=30, max_shot_seconds=0, transition='none',
                    background_video='', music_volume=0, sound_effects=False,
                    caption_emoji=False, color_grade='none', ken_burns=False,
                    end_cta='', watermark='none', hook_overlay=False,  # Keep title area blank in every Short; preserve word captions.
                    upload=False, also_languages=[], localize_metadata=[], notify_webhook='',
                    workers=1, crf=18, preset='medium', target_seconds=24)  # Bootstrap only; topic-adaptive duration set after footage/evidence
        from short_caption_style import lock_settings
        s=lock_settings(s)
        stage = 'production'
        studio = Studio(s)
        if os.environ.get('PURFFLE_MEDIA_FIRST', '1') == '1':
            # V4 ROOT FIX: verified factual script FIRST, then explicit
            # scene-by-scene real-video contracts, then the approved narration.
            # Old palette-first gathered vaguely related clips and forced a
            # fixed science story over them (#84 ship, #86 volcano).
            from media_first import (prepare_verified_palette, validate_narration_timing)
            from science_sources import (discover_evidence, screen_narration, use_evidence,
                                         use_review_feedback, rejected_claim_feedback)
            stage = 'science_sources'
            try:
                evidence = discover_evidence(os.environ['VIDEO_TOPIC'], s.language)
            except RuntimeError as source_error:
                from science_sources import write_source_failure
                write_source_failure(str(source_error),
                                     os.environ.get('SCIENCE_REPORT', 'science-report.json'))
                raise

            stage = 'grounded_script'
            review_feedback_text = ''
            review_scene_target = None
            for attempt in range(3):
                # The normalizer obtains precise, source-checked facts before
                # anybody searches for clips. A visual query can never
                # introduce an unsourced scientific claim into the speech.
                from visual_director import use_story_scene_target
                from fact_checked_topics import (verified_documentary_kind,
                                                 _lightning_repeated_topic)
                # An existing exact-source three-scene factual variant is
                # preferable to demanding four independent stock clips.
                topic = os.environ['VIDEO_TOPIC']
                verified_kind = verified_documentary_kind(topic)
                # When the approved source facts fit two short scenes, do
                # not insist on a third unrelated filler clip. Production
                # #89 found two genuine HD aurora clips and failed at 2/3.
                # #91: the five scarce-footage dossiers have complete
                # concise two-scene factual variants, not a truncated 3-shot
                # story. Requiring a third stock clip needlessly failed 4/5
                # of those scenes. Never shorten a topic without an approved
                # full explanatory script.
                concise_kinds = {
                    "mirror_condensation", "iceberg_breakup",
                    "whale_breaching", "lightning_thunder_delay",
                    "ocean_glow_bioluminescence",
                }
                target_count = (2 if verified_kind == "northern_lights_glow"
                                else 2 if verified_kind in concise_kinds
                                else 3 if (verified_kind or
                                           _lightning_repeated_topic(topic))
                                else review_scene_target)
                try:
                    with (use_story_scene_target(target_count),
                          use_evidence(evidence),
                          use_review_feedback(review_feedback_text)):
                        # For fixed, official-source-backed explainers,
                        # drafting a random Groq script only to overwrite
                        # every sentence wastes thousands of free tokens.
                        # Unknown topics still use model drafts and strict
                        # independent source-quote review.
                        from official_draft import approved_dossier_draft
                        cached_draft = approved_dossier_draft(
                            topic, s.language, evidence,
                            scene_count=target_count or 3)
                        if cached_draft is not None:
                            screenplay, pick, writer = cached_draft
                            print('[SOURCE DOSSIER] Factual source-reviewed '
                                  'draft; zero Groq script tokens', flush=True)
                        else:
                            screenplay, pick, writer = studio.draft(
                                topic, style='facts')
                except (ValueError, TypeError) as draft_error:
                    # The Groq JSON generator sometimes omits a mandatory
                    # scene action/key. Never fabricate one or waive the
                    # six-field visual schema; redraft inside the same
                    # bounded three-attempt factual/storyboard loop.
                    if attempt >= 2:
                        raise
                    logging.warning(
                        'Structured script rejected; requesting complete '
                        'scene fields (%s)', str(draft_error)[:180])
                    stage = 'grounded_script'
                    continue
                try:
                    from science_fact_guard import validate_unsourced_quantities
                    validate_unsourced_quantities(
                        screenplay, os.environ['VIDEO_TOPIC'])
                    from retention_storyboard import audit_storyboard
                    storyboard_audit = audit_storyboard(
                        os.environ['VIDEO_TOPIC'], screenplay, s.language)
                    stage = 'science_review'
                    screen_narration(
                        screenplay, evidence, studio.llm,
                        path=os.environ.get('SCIENCE_REPORT', 'science-report.json'))
                    break
                except RuntimeError as script_error:
                    if evidence.method == 'curated_editor_reviewed':
                        # A mismatched predefined statement cannot be fixed
                        # by paying the LLM to invent an alternative: fail
                        # closed and report the dossier integrity error.
                        raise
                    # An unavailable/malformed reviewer is a tool failure,
                    # not an unsupported factual claim. Another newly written
                    # storyboard cannot fix that tool and wastes free API
                    # quota; keep the failure honest and stop immediately.
                    if str(script_error).startswith('science_review_unavailable:'):
                        raise
                    if (str(script_error).startswith(
                            'science_claim_unverified: unsupported narration scene')):
                        feedback_path = os.environ.get(
                            'SCIENCE_REPORT', 'science-report.json')
                        review_feedback_text = rejected_claim_feedback(
                            feedback_path, screenplay)
                        # Use fewer genuinely supported factual statements
                        # instead of inventing four separate 'facts' when the
                        # available references can only support two or three.
                        # Still require a complete answer and independent
                        # sentence-level source review on every next attempt.
                        from science_sources import source_revision_scene_count
                        revision_count = source_revision_scene_count(
                            feedback_path, screenplay)
                        if revision_count is not None:
                            review_scene_target = revision_count
                        # Preserve why earlier scripts failed. A later 429
                        # overwrote science-report.json with an empty checks
                        # list, erasing the exact unsupported scene evidence.
                        # Keep at most two bounded same-job review snapshots
                        # in the normal finished/<video> artifact directory.
                        try:
                            source_report = Path(feedback_path)
                            if source_report.is_file():
                                snapshot = source_report.with_name(
                                    source_report.stem + f'-attempt-{attempt + 1}'
                                    + source_report.suffix)
                                snapshot.write_bytes(source_report.read_bytes())
                        except OSError:
                            pass  # Diagnostic archival never bypasses QA.
                    if attempt >= 2:
                        # The real V5 #102 proof screened two of four scenes
                        # as true, then discarded them because the other two
                        # contained unsourced assertions. Reuse *only* fully
                        # approved source-checked scenes, with their original
                        # exact narration and visual intent. Do NOT add a new
                        # LLM science story. The new concise storyboard must
                        # pass editorial, numerical, and independent science
                        # review before any video can be accepted.
                        if not str(script_error).startswith(
                                'science_claim_unverified: unsupported narration scene'):
                            raise
                        from science_salvage import salvage_approved_narration
                        salvaged = salvage_approved_narration(
                            screenplay, feedback_path)
                        if salvaged is None:
                            raise
                        print('[SCIENCE RECOVERY] Retain only genuinely '
                              'source-screened narration scenes; recheck '
                              'concise storyboard', flush=True)
                        validate_unsourced_quantities(
                            salvaged, os.environ['VIDEO_TOPIC'])
                        storyboard_audit = audit_storyboard(
                            os.environ['VIDEO_TOPIC'], salvaged, s.language)
                        stage = 'science_review'
                        screen_narration(
                            salvaged, evidence, studio.llm,
                            path=os.environ.get('SCIENCE_REPORT', 'science-report.json'))
                        screenplay = salvaged
                        break
                    logging.warning(
                        'Source/factuality/storyboard screen rejected draft (%s); '
                        'requesting one more source-grounded script',
                        str(script_error)[:200])
                    stage = 'grounded_script'

            from short_recovery import save_reviewed_script
            save_reviewed_script(screenplay, s.language, os.environ['VIDEO_TOPIC'])
            stage = 'visual_director_preflight'
            # Script comes first, so the required real-video count is exactly
            # the number of actual factual sentences. No empty/duplicated
            # "filler" clips may be inserted to reach an arbitrary target.
            script_scene_count = len(screenplay.scenes)
            if not 2 <= script_scene_count <= 6:
                raise RuntimeError("visual_director_invalid_scene_count")
            # A real-video preflight may fail because the source library
            # cannot film one of the draft's literal actions. Give the factual
            # writer ONE feedback-guided revision, not an unbounded retry.
            # Restore scene reservations before trying the revised storyboard:
            # an unsuccessful draft must not consume clips that could serve it.
            ledger_path = Path(os.environ.get(
                'FOOTAGE_USED_PATH', 'media_cache/used-media.json'))
            ledger_before = (ledger_path.read_bytes()
                             if ledger_path.is_file() else None)
            try:
                palette = prepare_verified_palette(
                    os.environ['VIDEO_TOPIC'], s, storyboard=screenplay,
                    min_scenes=script_scene_count, max_scenes=script_scene_count,
                    clip_seconds=10.0)
            except RuntimeError as footage_error:
                if 'media_preflight_insufficient_footage' not in str(footage_error):
                    raise
                from media_first import footage_failure_feedback
                from visual_director import use_footage_feedback
                report_path = Path(os.environ.get(
                    'FOOTAGE_REPORT', 'footage-report.json'))
                failure_report = json.loads(
                    report_path.read_text(encoding='utf-8'))
                feedback = footage_failure_feedback(failure_report)
                if not feedback:
                    raise
                def restore_used_media():
                    # Rejected visual plans must not reserve footage for the
                    # next attempt. This uses the exact preflight ledger copy.
                    if ledger_before is None:
                        ledger_path.unlink(missing_ok=True)
                    else:
                        ledger_path.parent.mkdir(parents=True, exist_ok=True)
                        temporary = ledger_path.with_suffix('.replan')
                        temporary.write_bytes(ledger_before)
                        temporary.replace(ledger_path)

                # FIRST fix only the unfilmable VISUAL directions. The
                # previously source-screened speech stays byte-for-byte
                # unchanged. This saves Groq tokens and avoids a second
                # fictitious 'light reflecting like a mirror' explanation.
                from visible_science_repair import visible_context_repair
                repaired = visible_context_repair(
                    screenplay, os.environ['VIDEO_TOPIC'],
                    failure_report.get('unavailable_scenes', []))
                restore_used_media()
                if repaired is not None:
                    print('[FOOTAGE RECOVERY] Retry camera-filmable sky context '
                          'WITHOUT rewriting verified narration', flush=True)
                    stage = 'visible_science_context_repair'
                    try:
                        palette = prepare_verified_palette(
                            os.environ['VIDEO_TOPIC'], s,
                            storyboard=repaired,
                            min_scenes=script_scene_count,
                            max_scenes=script_scene_count,
                            clip_seconds=10.0)
                    except RuntimeError as context_error:
                        if 'media_preflight_insufficient_footage' not in str(context_error):
                            raise
                        # A failed visual-only attempt cannot block the
                        # source-grounded narrative fallback from using
                        # potentially suitable previously tested stock.
                        restore_used_media()
                        repaired = None
                if repaired is not None:
                    screenplay = repaired
                else:
                    # An approved fixed-science dossier must not be rewritten
                    # with untrusted model claims merely to obtain footage.
                    # Subject/license/CLIP gates still fail closed.
                    if evidence.method == 'curated_editor_reviewed':
                        raise
                    print('[FOOTAGE RECOVERY] One source-grounded storyboard '
                          'revision after failed visual preflight', flush=True)
                    stage = 'grounded_visual_replan'
                    with (use_story_scene_target(script_scene_count),
                          use_evidence(evidence), use_footage_feedback(feedback)):
                        alternative, alt_pick, alt_writer = studio.draft(
                            os.environ['VIDEO_TOPIC'], style='facts')
                    if len(alternative.scenes) != script_scene_count:
                        raise RuntimeError(
                            'visual_replan_scene_count_mismatch')
                    if all(
                        str(a.visual_search_query).casefold() ==
                        str(b.visual_search_query).casefold()
                        for a, b in zip(alternative.scenes, screenplay.scenes)
                    ):
                        raise RuntimeError(
                            'visual_replan_repeated_unavailable_queries')
                    # A new factual script still needs independent source
                    # screening. Visual-only repair above never changes speech.
                    validate_unsourced_quantities(
                        alternative, os.environ['VIDEO_TOPIC'])
                    storyboard_audit = audit_storyboard(
                        os.environ['VIDEO_TOPIC'], alternative, s.language)
                    stage = 'science_review'
                    screen_narration(
                        alternative, evidence, studio.llm,
                        path=os.environ.get('SCIENCE_REPORT', 'science-report.json'))
                    save_reviewed_script(alternative, s.language, os.environ['VIDEO_TOPIC'])
                    stage = 'visual_director_preflight'
                    palette = prepare_verified_palette(
                        os.environ['VIDEO_TOPIC'], s, storyboard=alternative,
                        min_scenes=script_scene_count,
                        max_scenes=script_scene_count,
                        clip_seconds=10.0)
                    screenplay, pick, writer = alternative, alt_pick, alt_writer
            validate_narration_timing(palette, screenplay, s.language)
            from retention_storyboard import choose_duration_seconds, save_storyboard_report
            fact_count = len(getattr(evidence, 'sources', []) or [])
            planned_seconds = choose_duration_seconds(
                os.environ['VIDEO_TOPIC'], script_scene_count,
                fact_count=fact_count)
            palette.planned_seconds = planned_seconds
            s = replace(s, target_seconds=planned_seconds)
            studio.s = s
            studio.clock.scale = max(.25, planned_seconds / 40)
            storyboard_audit = audit_storyboard(
                os.environ['VIDEO_TOPIC'], screenplay, s.language,
                planned_seconds=planned_seconds)
            save_storyboard_report(
                os.environ.get('RETENTION_REPORT',
                               str(target.with_name('retention-report.json'))),
                storyboard_audit)
            logging.info('V4 factual storyboard %d scenes matched %d independently '
                         'verified unique moving footage clips, duration goal=%ds',
                         script_scene_count, len(palette.items), planned_seconds)
            stage = 'production'
            # Voice identity/audio/word captions policy is UNCHANGED. Upstream
            # consumes only fully screened local media_map paths, not URLs.
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
        stage = 'full_timeline_qa'
        from output_qa import validate_timeline
        from purffle_shorts.pipeline import END_PAD
        voice_data = json.loads(voice_report.read_text(encoding='utf8'))
        script_data = json.loads((folder / 'script.json').read_text(encoding='utf8'))
        expected_text = ' '.join(scene['narration'] for scene in script_data['scenes'])
        full_qa = validate_timeline(video, folder / 'captions.srt',
            expected_size=(s.width, s.height),
            expected_duration=float(voice_data['duration']) + END_PAD,
            expected_text=expected_text)
        write_json(target.with_name('output-qa.json'), full_qa)
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
