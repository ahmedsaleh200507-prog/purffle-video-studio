import json
from pathlib import Path
from unittest.mock import patch

import pytest
import batch


def test_language_and_raw_topic():
    assert batch.parse_topic('de|Warum ist der Himmel blau?') == ('de', 'Warum ist der Himmel blau?')
    assert batch.parse_topic('en|A | B') == ('en', 'A | B')
    assert batch.parse_topic('de Thema') == ('de', 'Thema')
    assert batch.parse_topic('hello') == ('en', 'hello')
    with pytest.raises(ValueError):
        batch.parse_topic('fr|bonjour')
    with pytest.raises(ValueError):
        batch.parse_topic('en| ')


def test_nonzero_worker_never_success_even_when_partial_mp4_exists(tmp_path):
    target = tmp_path / 'video_01'
    target.mkdir()
    (target / 'partial.mp4').write_bytes(b'partial output')
    (target / 'job-result.json').write_text(json.dumps({'status': 'ok', 'mp4': str(target / 'partial.mp4')}))
    with patch('batch.subprocess.Popen') as popen:
        popen.return_value.returncode = 1
        result = batch.run_job(1, 'en|test', tmp_path)
    assert result['status'] == 'failed'
    assert result['mp4'] is None
    assert not (target / 'job-result.json').exists()
    assert (target / 'report.json').exists()


def test_batch_continues_but_partial_failure_nonzero(tmp_path, monkeypatch):
    monkeypatch.setattr(batch, 'ROOT', tmp_path)
    for index in range(1, 11):
        monkeypatch.delenv(f'INPUT_{index}', raising=False)
    monkeypatch.setenv('INPUT_1', 'en|first')
    monkeypatch.setenv('INPUT_2', 'de|zweite')
    calls = []
    def job(index, *args):
        calls.append(index)
        return {'index': index, 'status': 'failed' if index == 1 else 'ok'}
    monkeypatch.setattr(batch, 'run_job', job)
    assert batch.main() == 1
    assert calls == [1, 2]
    assert len(json.loads((tmp_path / 'batch-results.json').read_text())) == 2


def test_workflow_contract():
    import yaml
    root = Path(__file__).resolve().parents[1]
    workflow = yaml.safe_load((root / '.github/workflows/videos.yml').read_text())
    # YAML1.1 treats 'on' as true; GitHub uses YAML1.2.
    inputs = workflow.get('on', workflow.get(True))['workflow_dispatch']['inputs']
    assert len(inputs) == 10
    job = workflow['jobs']['create-videos']
    assert job['env']['RESOLUTION'] == '1080x1920'
    assert job['permissions'] if 'permissions' in job else workflow['permissions'] == {'contents': 'read'}
    production = next(x for x in job['steps'] if x.get('name') == 'Produce up to 10 videos')
    assert production['env']['PURFFLE_STRICT'] == '1'
    artifact = next(x for x in job['steps'] if x.get('uses', '').startswith('actions/upload-artifact'))
    assert artifact['if'] == 'always()'
    assert '${{ inputs.' not in str([x.get('run', '') for x in job['steps']])
