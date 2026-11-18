"""Run 1–10 independent jobs; preserve diagnostics and fail on any failed video."""
from __future__ import annotations

import json
import os
import signal
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    content = json.dumps(value, ensure_ascii=False, indent=2)
    for name in ('GROQ_API_KEY', 'PIXABAY_API_KEY', 'PEXELS_API_KEY', 'COVERR_API_KEY', 'EUROPEANA_API_KEY', 'GITHUB_TOKEN', 'GH_TOKEN', 'HF_TOKEN'):
        secret = os.environ.get(name, '')
        if secret:
            content = content.replace(secret, '[REDACTED]')
    tmp.write_text(content, encoding='utf-8')
    tmp.replace(path)


def parse_topic(raw: str):
    raw = raw.strip()
    if raw.lower().startswith(('de|', 'en|')):
        lang, topic = raw.split('|', 1)
        lang, topic = lang.strip().lower(), topic.strip()
    elif '|' in raw and raw.split('|', 1)[0].strip().lower() in ('fr', 'es', 'it'):
        raise ValueError('Language prefix must be en| or de|')
    elif raw[:3].lower() in ('de ', 'en '):
        lang, topic = raw[:2].lower(), raw[3:].strip()
    else:
        # Infer German for unprefixed German prose instead of silently
        # synthesizing an English voice. Explicit de| / en| always wins.
        import re
        german_markers = re.findall(
            r"\b(?:die|der|das|und|eine|einer|wurden|welcher|diese|doch|vor|jahrhunderten|geheimnisse|menschen|orte|ich|du|wir|nicht|mehr|warum|beim|zwischen|wieder|plötzlich|gehst|weißt|vergessen|küche|gehirn)\b",
            raw.lower(),
        )
        lang, topic = ('de' if len(german_markers) >= 3 or
                       any(ch in raw for ch in 'äöüßÄÖÜ') else 'en'), raw
    if not topic or len(topic) > 2000:
        raise ValueError('Topic must contain 1–2000 characters')
    return lang, topic


def _rejection_category(reason: str) -> str:
    """Classify one actual candidate rejection rather than unrelated API logs."""
    reason = str(reason).lower()
    categories = (
        ("metadata_rejected", ("scene metadata lacks", "metadata does not describe")),
        ("semantic_mismatch", ("visual scene mismatch", "visual mismatch")),
        ("insufficient_native_resolution", ("insufficient_native_resolution", "below 720 short side", "requires short side")),
        ("insufficient_duration", ("without looping", "source too short")),
        ("license_rejected", ("incompatible candidate license", "license provenance")),
        ("no_motion", ("insufficiently moving", "static or", "no moving video stream")),
        ("download_invalid", ("invalid video", "download failed", "corrupt")),
    )
    return next((label for label, parts in categories
                 if any(part in reason for part in parts)), "other")


def classify_failure(message: str, log_text: str = "", details=None) -> str:
    """Use root worker error and actual scene rejections before incidental logs."""
    direct = str(message).lower()
    # Prefer exact V3 preflight errors over unrelated 'rate limit' text in
    # provider-health summaries; #71 had ZERO provider search attempts.
    for prefix, category in (
        ("media_preflight_no_topic_palette", "topic_palette_empty"),
        ("media_preflight_insufficient_footage", "insufficient_verified_clips"),
        ("unverified_quantitative_claim", "unverified_factual_claim"),
    ):
        if prefix in direct:
            return category
    full_log = str(log_text)[-24000:].lower()
    if "no suitable verified real video" in direct or "no verified real video" in direct:
        category_counts = (details or {}).get("rejection_categories") or {}
        relevant = {k: v for k, v in category_counts.items()
                    if k not in ("other", "non_video_or_duplicate") and v > 0}
        if relevant:
            return max(relevant, key=lambda key: relevant[key])
        if "scene metadata" in full_log:
            return "metadata_rejected"
        return "no_candidates"
    combined = direct + chr(10) + full_log
    checks = (
        # Legacy static smoke tests rely on these precise generic labels.
        # Specific footage/voice failures below use the richer categories.
        ("timeout", ("video timed out after",)),
        ("source_not_found", ("no suitable footage found",)),
        ("provider_auth", ("http_401", "http_403", "http 401", "http 403", "unauthorized", "forbidden")),
        ("provider_rate_limit", ("http_429", "http 429", "rate limit", "quota exceeded", "circuit_open")),
        ("provider_timeout", ("provider timeout", "network_or_json_error", "api request or json parsing failed")),
        ("missing_api_key", ("api_key missing", "api key missing", "groq_api_key missing", "missing pexels_api_key")),
        ("insufficient_native_resolution", ("insufficient_native_resolution", "portrait crop would upscale")),
        ("metadata_rejected", ("scene metadata lacks", "scene metadata does not describe")),
        ("semantic_mismatch", ("visual scene mismatch", "unrelated metadata")),
        ("license_rejected", ("unverified or incompatible candidate license", "missing license provenance")),
        ("insufficient_duration", ("without looping", "source too short")),
        ("no_motion", ("insufficiently moving", "static or", "no moving video stream")),
        ("download_invalid", ("invalid video", "download failed", "corrupt", "invalid media")),
        ("voice_timeout", ("tts deadline exceeded", "voice deadline exceeded", "edge tts deadline")),
        ("voice_invalid", ("free narration failed", "voice alignment", "narration audio is missing")),
        ("render_failure", ("ffmpeg", "ffprobe", "render refused", "output resolution mismatch")),
        ("no_candidates", ("no suitable verified real video", "no candidates", "no verified real video")),
        ("provider_access", ("provider disabled", "unsupported provider")),
        ("unexpected", ("traceback", "worker exited with status", "exception")),
    )
    return next((category for category, patterns in checks
                 if any(pattern in combined for pattern in patterns)), "unknown")


def failure_details(target: Path):
    """Retain the failing scene and provider evidence without hiding the worker error."""
    details = {}
    job_file = target / 'job-result.json'
    if job_file.is_file():
        try:
            worker = json.loads(job_file.read_text(encoding='utf-8'))
            for field in ('stage', 'exception_type', 'error'):
                if worker.get(field):
                    details[field] = worker[field]
        except (ValueError, OSError):
            pass
    footage_file = target / 'footage-report.json'
    if footage_file.is_file():
        try:
            report = json.loads(footage_file.read_text(encoding='utf-8'))
            scenes = report.get('scenes') or []
            failed = [s for s in scenes if s.get('status') == 'failed']
            if failed:
                scene = failed[-1]
                details['scene'] = scene.get('index')
                details['query'] = scene.get('plan', {}).get('visual_search_query', '')
                rejections = scene.get('rejections') or []
                # Retries of one logical scene are separate report entries.
                # Count reasons from all attempts of the actual failed scene.
                attempted = [s for s in scenes if s.get('index') == scene.get('index')
                             and s.get('status') == 'failed']
                all_rejections = [rej for attempt in attempted
                                  for rej in attempt.get('rejections', [])]
                categories = {}
                for rej in all_rejections:
                    reason = str(rej.get('reason', ''))
                    group = (_rejection_category(reason) if "non_video_or_duplicate" not in reason
                             else "non_video_or_duplicate")
                    categories[group] = categories.get(group, 0) + 1
                details['rejection_categories'] = categories
                details['rejection_count'] = len(all_rejections)
                details['latest_rejections'] = all_rejections[-8:]
                providers = [r.get('source') for r in rejections if r.get('source')]
                details['provider'] = providers[-1] if providers else None
            details['provider_events'] = (report.get('provider_events') or [])[-12:]
            details['footage_state'] = report.get('state', 'unknown')
        except (ValueError, OSError):
            pass
    voice_file = target / 'voice-report.json'
    if voice_file.is_file():
        try:
            voice = json.loads(voice_file.read_text(encoding='utf-8'))
            if voice.get('state') == 'failed':
                details['voice_attempts'] = voice.get('attempts', [])
        except (ValueError, OSError):
            pass
    return details


def resume_completed_job(index: int, raw: str, out: Path):
    """Reuse only a matching, previously validated video that still probes correctly."""
    if os.environ.get('PURFFLE_RESUME', '1') != '1':
        return None
    target = out / f'video_{index:02d}'
    report = target / 'report.json'
    if not report.is_file():
        return None
    try:
        prior = json.loads(report.read_text(encoding='utf-8'))
        if (prior.get('status') != 'ok' or prior.get('original_input') != raw
                or not prior.get('mp4')):
            return None
        video = Path(prior['mp4'])
        if not video.is_file() or video.stat().st_size < 1024:
            return None
        probe = subprocess.run(['ffprobe', '-v', 'error', '-show_streams',
                                '-show_format', '-of', 'json', str(video)],
                               capture_output=True, text=True, check=True, timeout=30)
        data = json.loads(probe.stdout)
        streams = data.get('streams', [])
        vid = next((s for s in streams if s.get('codec_type') == 'video'), None)
        audio = any(s.get('codec_type') == 'audio' for s in streams)
        w, h = (int(v) for v in os.environ.get('RESOLUTION', '720x1280').split('x'))
        if (not vid or not audio or (int(vid.get('width', 0)), int(vid.get('height', 0))) != (w, h)
                or float(data.get('format', {}).get('duration') or 0) <= 0):
            return None
        print(f'[VIDEO RESUMED] index={index} validated existing output={video}', flush=True)
        return prior
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        return None


def run_job(index: int, raw: str, out: Path, timeout: int = 1500):
    target = out / f'video_{index:02d}'
    target.mkdir(parents=True, exist_ok=True)
    result = {'index': index, 'topic': raw, 'original_input': raw, 'status': 'failed', 'mp4': None}
    started = time.monotonic()
    log_path = target / 'purffle.log'
    try:
        lang, topic = parse_topic(raw)
        result.update(language=lang, topic=topic)
        env = os.environ.copy()
        env.update(PURFFLE_STRICT='1', LANGUAGE=lang, VIDEO_TOPIC=topic,
                   FOOTAGE_REPORT=str((target / 'footage-report.json').resolve()),
                   MEDIA_FIRST_REPORT=str((target / 'media-first-plan.json').resolve()),
                   MEDIA_FIRST_WORK_DIR=str((target / 'media-first-work').resolve()),
                   PURFFLE_MEDIA_FIRST=os.environ.get('PURFFLE_MEDIA_FIRST', '1'),
                   VOICE_REPORT=str((target / 'voice-report.json').resolve()),
                   SCIENCE_REPORT=str((target / 'science-report.json').resolve()),
                   JOB_RESULT=str((target / 'job-result.json').resolve()),
                   OUTPUT_DIR=str((target / 'render').resolve()),
                   PYTHONPATH=os.pathsep.join([str(ROOT), str(ROOT / 'scripts')]),
                   OMP_NUM_THREADS='2', MKL_NUM_THREADS='2', TOKENIZERS_PARALLELISM='false')
        # No stale result can turn an unsuccessful retry into success.
        Path(env['JOB_RESULT']).unlink(missing_ok=True)
        print(f'[VIDEO START] index={index} language={lang} topic={topic!r}', flush=True)
        with log_path.open('w', encoding='utf-8') as log:
            proc = subprocess.Popen([sys.executable, str(ROOT / 'scripts/render_job.py')],
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env,
                                    cwd=ROOT, start_new_session=True)
            def relay():
                for line in proc.stdout:
                    for name in ('GROQ_API_KEY', 'PIXABAY_API_KEY', 'PEXELS_API_KEY', 'COVERR_API_KEY', 'EUROPEANA_API_KEY', 'GITHUB_TOKEN', 'GH_TOKEN', 'HF_TOKEN'):
                        secret = env.get(name, '')
                        if secret:
                            line = line.replace(secret, '[REDACTED]')
                    log.write(line)
                    log.flush()
                    print(line, end='', flush=True)
            reader = threading.Thread(target=relay, daemon=True)
            reader.start()
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
                raise RuntimeError(f'Video timed out after {timeout}s; entire process group stopped')
            finally:
                reader.join(timeout=5)
        if proc.returncode:
            worker = failure_details(target)
            raise RuntimeError(worker.get('error') or f'Worker exited with status {proc.returncode}')
        job = json.loads(Path(env['JOB_RESULT']).read_text(encoding='utf-8'))
        if job.get('status') != 'ok' or not job.get('mp4') or not Path(job['mp4']).is_file():
            raise RuntimeError('Worker did not provide a validated successful MP4')
        result.update(job)
        # A missing Shorts title must never undo a successfully validated MP4.
        try:
            from youtube_metadata import attach_title_to_video
            attach_title_to_video(result)
        except (OSError, ValueError, TypeError) as title_exc:
            result["youtube_title_error"] = type(title_exc).__name__
    except Exception as exc:
        result.update(status='failed', error=str(exc), exception_type=type(exc).__name__, mp4=None)
    finally:
        if result['status'] != 'ok':
            # Partial output/title from an unsuccessful retry is not publishable.
            for partial in (target / 'render').rglob('*.mp4'):
                partial.unlink(missing_ok=True)
            for stale_title in (target / 'render').rglob('YouTube_Title.txt'):
                stale_title.unlink(missing_ok=True)
        # Download paths in the report are provenance; raw sources are transient.
        # Do this only after the worker/process group has stopped and rendered.
        shutil.rmtree(ROOT / 'media_cache' / 'downloads', ignore_errors=True)
        result['seconds'] = round(time.monotonic() - started, 1)
        result['log'] = str(log_path)
        write_json(target / 'report.json', result)
        if log_path.exists():
            lines = log_path.read_text(errors='replace').splitlines()
            if result['status'] != 'ok':
                details = failure_details(target)
                result['failure_details'] = details
                result['stage'] = details.get('stage', 'unknown')
                result['failure_category'] = classify_failure(
                    result.get('error', ''),
                    chr(10).join(lines) + chr(10) +
                    chr(10).join(str(x.get('reason', '')) for x in details.get('latest_rejections', [])) +
                    chr(10).join(str(x.get('error', '')) for x in details.get('voice_attempts', [])),
                    details)
                write_json(target / 'report.json', result)
            selected = [x for x in lines if any(s in x for s in ('[SOURCE', '[SELECTED', '[REJECT', '[SCENE'))]
            print('\n'.join(selected), flush=True)
            if result['status'] != 'ok':
                print('\n'.join(lines[-50:]), flush=True)
        print(f"[VIDEO END] index={index} status={result['status']}", flush=True)
    return result



def write_consolidated_diagnostics(out: Path, results: list):
    """One shareable, redacted report for the entire batch, including failures."""
    lines = [
        "PURFFLE VIDEO STUDIO - CONSOLIDATED DIAGNOSTICS",
        "Generated by scripts/batch.py; no API keys or tokens included.",
        "Videos requested: " + str(len(results)),
        "Succeeded: " + str(sum(r.get('status') == 'ok' for r in results)),
        "Failed: " + str(sum(r.get('status') != 'ok' for r in results)),
        "",
    ]
    for result in results:
        index = result['index']
        target = out / f'video_{index:02d}'
        lines.extend([
            "=" * 68,
            f"VIDEO {index}: {result.get('status', 'unknown').upper()}",
            "Topic: " + str(result.get('topic', '')),
            "Language: " + str(result.get('language', 'unknown')),
            "Failure category: " + str(result.get('failure_category', 'none')),
            "Error: " + str(result.get('error', 'none')),
            "Output: " + str(result.get('mp4', 'none')),
        ])
        for name in ('footage-report.json', 'voice-report.json', 'job-result.json'):
            path = target / name
            if path.is_file():
                try:
                    report = json.loads(path.read_text(encoding='utf-8'))
                    lines.append(f"--- {name} ---")
                    lines.append(json.dumps(report, ensure_ascii=False, indent=2, default=str)[:60000])
                except (OSError, ValueError) as exc:
                    lines.append(f"{name}: unreadable ({type(exc).__name__})")
        log = target / 'purffle.log'
        if log.is_file():
            text = log.read_text(encoding='utf-8', errors='replace')
            interesting = ('error', 'failed', 'reject', 'timeout', 'deadline',
                           'source check', 'selected', 'b-roll', 'traceback',
                           'exception', 'video end', 'voice', 'footage')
            selected = [line for line in text.splitlines()
                        if any(term in line.lower() for term in interesting)]
            lines.append("--- Relevant production log (last 160 matching lines) ---")
            lines.extend(selected[-160:])
        lines.append("")
    # Reuse the existing atomic writer's secret-redaction policy.
    destination = ROOT / 'PURFFLE_DIAGNOSTICS.txt'
    content = "\n".join(lines) + "\n"
    for key in ('GROQ_API_KEY', 'PIXABAY_API_KEY', 'PEXELS_API_KEY',
                'COVERR_API_KEY', 'EUROPEANA_API_KEY', 'GITHUB_TOKEN',
                'GH_TOKEN', 'HF_TOKEN'):
        secret = os.environ.get(key, '')
        if secret:
            content = content.replace(secret, '[REDACTED]')
    tmp = destination.with_suffix('.tmp')
    tmp.write_text(content, encoding='utf-8')
    tmp.replace(destination)
    details = []
    for result in results:
        target = out / f"video_{result['index']:02d}"
        summary = {'result': result}
        for name, field in (('footage-report.json', 'footage'),
                            ('voice-report.json', 'voice'),
                            ('job-result.json', 'worker')):
            path = target / name
            if path.is_file():
                try:
                    summary[field] = json.loads(path.read_text(encoding='utf-8'))
                except (OSError, ValueError):
                    summary[field] = {'error': 'unreadable'}
        details.append(summary)
    write_json(ROOT / 'PURFFLE_DIAGNOSTICS.json', {
        'schema_version': 1,
        'summary': {'requested': len(results),
                    'succeeded': sum(r.get('status') == 'ok' for r in results),
                    'failed': sum(r.get('status') != 'ok' for r in results)},
        'videos': details,
    })
    print(f'[DIAGNOSTICS] {destination} ({destination.stat().st_size} bytes)', flush=True)


def main():
    out = ROOT / 'finished'
    out.mkdir(exist_ok=True)
    results = []
    for index in range(1, 11):
        raw = os.environ.get(f'INPUT_{index}', '').strip()
        if not raw:
            continue
        result = resume_completed_job(index, raw, out) or run_job(index, raw, out)
        # Existing successfully rendered MP4s may predate this new upload file.
        if result.get('status') == 'ok' and not result.get('youtube_title'):
            try:
                from youtube_metadata import attach_title_to_video
                attach_title_to_video(result)
                write_json(out / f"video_{index:02d}" / 'report.json', result)
            except (OSError, ValueError, TypeError) as title_exc:
                result["youtube_title_error"] = type(title_exc).__name__
        results.append(result)
        write_json(ROOT / 'batch-results.json', results)
        write_consolidated_diagnostics(out, results)
        from youtube_metadata import write_batch_titles
        write_batch_titles(ROOT, results)
    if not results:
        write_json(ROOT / 'batch-results.json', [])
        print('No video topics supplied', flush=True)
    ok = sum(r['status'] == 'ok' for r in results)
    print(f'[BATCH RESULT] succeeded={ok} failed={len(results)-ok}', flush=True)
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary, 'a', encoding='utf-8') as f:
            f.write(f'## Purffle V2\n\n{ok}/{len(results)} videos succeeded.\n\n')
            for r in results:
                f.write(f"- Video {r['index']}: **{r['status']}** — {r.get('error', r.get('mp4', ''))}\n")
    return 0 if results and ok == len(results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
