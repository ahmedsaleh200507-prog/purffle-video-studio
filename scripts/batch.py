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
    for name in ('GROQ_API_KEY', 'PIXABAY_API_KEY', 'PEXELS_API_KEY', 'COVERR_API_KEY', 'EUROPEANA_API_KEY'):
        secret = os.environ.get(name, '')
        if secret:
            content = content.replace(secret, '[REDACTED]')
    tmp.write_text(content, encoding='utf-8')
    tmp.replace(path)


def parse_topic(raw: str):
    raw = raw.strip()
    if '|' in raw:
        lang, topic = raw.split('|', 1)
        if lang.strip().lower() not in ('de', 'en'):
            raise ValueError('Language prefix must be en| or de|')
        lang, topic = lang.strip().lower(), topic.strip()
    elif raw[:3].lower() in ('de ', 'en '):
        lang, topic = raw[:2].lower(), raw[3:].strip()
    else:
        lang, topic = 'en', raw
    if not topic or len(topic) > 2000:
        raise ValueError('Topic must contain 1–2000 characters')
    return lang, topic


def run_job(index: int, raw: str, out: Path, timeout: int = 1500):
    target = out / f'video_{index:02d}'
    target.mkdir(parents=True, exist_ok=True)
    result = {'index': index, 'topic': raw, 'status': 'failed', 'mp4': None}
    started = time.monotonic()
    log_path = target / 'purffle.log'
    try:
        lang, topic = parse_topic(raw)
        result.update(language=lang, topic=topic)
        env = os.environ.copy()
        env.update(PURFFLE_STRICT='1', LANGUAGE=lang, VIDEO_TOPIC=topic,
                   FOOTAGE_REPORT=str((target / 'footage-report.json').resolve()),
                   VOICE_REPORT=str((target / 'voice-report.json').resolve()),
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
                    for name in ('GROQ_API_KEY', 'PIXABAY_API_KEY', 'PEXELS_API_KEY', 'COVERR_API_KEY', 'EUROPEANA_API_KEY'):
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
            raise RuntimeError(f'Worker exited with status {proc.returncode}')
        job = json.loads(Path(env['JOB_RESULT']).read_text(encoding='utf-8'))
        if job.get('status') != 'ok' or not job.get('mp4') or not Path(job['mp4']).is_file():
            raise RuntimeError('Worker did not provide a validated successful MP4')
        result.update(job)
    except Exception as exc:
        result.update(status='failed', error=str(exc), mp4=None)
    finally:
        if result['status'] != 'ok':
            # Partial render output is diagnostic failure, never a deliverable.
            for partial in (target / 'render').rglob('*.mp4'):
                partial.unlink(missing_ok=True)
        # Download paths in the report are provenance; raw sources are transient.
        # Do this only after the worker/process group has stopped and rendered.
        shutil.rmtree(ROOT / 'media_cache' / 'downloads', ignore_errors=True)
        result['seconds'] = round(time.monotonic() - started, 1)
        result['log'] = str(log_path)
        write_json(target / 'report.json', result)
        if log_path.exists():
            lines = log_path.read_text(errors='replace').splitlines()
            selected = [x for x in lines if any(s in x for s in ('[SOURCE', '[SELECTED', '[REJECT', '[SCENE'))]
            print('\n'.join(selected), flush=True)
            if result['status'] != 'ok':
                print('\n'.join(lines[-50:]), flush=True)
        print(f"[VIDEO END] index={index} status={result['status']}", flush=True)
    return result


def main():
    out = ROOT / 'finished'
    out.mkdir(exist_ok=True)
    results = []
    for index in range(1, 11):
        raw = os.environ.get(f'INPUT_{index}', '').strip()
        if not raw:
            continue
        results.append(run_job(index, raw, out))
        write_json(ROOT / 'batch-results.json', results)
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
