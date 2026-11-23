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
    assert batch.parse_topic('Kennst du das? Du gehst in die Küche und plötzlich weißt du nicht mehr, warum du dort bist.') [0] == 'de'
    assert batch.parse_topic('The answer is A | B') == ('en', 'The answer is A | B')
    assert batch.parse_topic('de|Warum? | Wieso?') == ('de', 'Warum? | Wieso?')
    with pytest.raises(ValueError):
        batch.parse_topic('fr|bonjour')
    with pytest.raises(ValueError):
        batch.parse_topic('en| ')


def test_nonzero_worker_never_success_even_when_partial_mp4_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(batch, 'ROOT', tmp_path)
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
    # A constant workflow-wide queue cancels older queued manual runs when a
    # user taps Run workflow more than once. Do not reintroduce it.
    assert 'concurrency' not in workflow
    assert workflow['run-name'].startswith('Purffle Shorts')
    triggers = workflow.get('on', workflow.get(True))
    assert set(triggers) == {'workflow_dispatch'}
    # Keep the familiar create-videos label in the Actions UI even though
    # 10 independent video jobs still render behind the scenes.
    assert workflow['jobs']['create-videos']['name'].startswith('create-videos | Video')
    assert workflow['jobs']['collect-results']['name'] == 'create-videos'
    job = workflow['jobs']['create-videos']
    assert job['env']['RESOLUTION'] == '1080x1920'
    assert job['permissions'] if 'permissions' in job else workflow['permissions'] == {'contents': 'read'}
    # Ten slots are queued independently; shared Groq quota requires one at a time.
    strategy = job['strategy']
    assert strategy['fail-fast'] is False
    assert strategy['max-parallel'] == 1
    slots = strategy['matrix']['include']
    assert [s['slot'] for s in slots] == list(range(1, 11))
    assert [s['input'] for s in slots] == [f'video_{i}' for i in range(1, 11)]
    assert all(f'INPUT_{i}' in job['env'] for i in range(1, 11))
    production = next(x for x in job['steps'] if x.get('name') == 'Produce selected video')
    assert production['env']['PURFFLE_STRICT'] == '1'
    assert production['if'] == "steps.selected.outputs.render == 'true'"
    artifact = next(x for x in job['steps'] if x.get('uses', '').startswith('actions/upload-artifact'))
    assert artifact['if'].startswith('always()')
    assert 'finished/' in artifact['with']['path']
    collector = workflow['jobs']['collect-results']
    assert collector['needs'] == 'create-videos'
    assert collector['if'] == 'always()'
    merged = next(x for x in collector['steps'] if x.get('uses', '').startswith('actions/download-artifact'))
    assert merged['with']['merge-multiple'] is True
    assert merged['with']['path'] == 'finished'
    combined = next(x for x in collector['steps'] if x.get('uses', '').startswith('actions/upload-artifact'))
    assert 'YOUTUBE_SHORTS_TITLES.txt' in combined['with']['path']
    assert '${{ inputs.' not in str([x.get('run', '') for x in job['steps']])


def test_production_85_rejects_ten_topics_in_one_slot_before_media():
    from batch import parse_topic
    combined = ("Why Can Giant Waves Overwhelm Ships? "
                "en|Why Do We See Lightning Before Hearing Thunder? "
                "en|What Makes a Volcano Suddenly Erupt?")
    with pytest.raises(ValueError, match="EXACTLY ONE topic"):
        parse_topic(combined)
    with pytest.raises(ValueError, match="EXACTLY ONE topic"):
        parse_topic("en|Why Do Icebergs Break Apart?" + chr(10)
                    + "en|Why Does the Ocean Glow?")
    assert parse_topic("en|Why Do Icebergs Break Apart?") == (
        "en", "Why Do Icebergs Break Apart?")


def test_production_85_matrix_respects_shared_free_groq_rate_limit():
    from pathlib import Path
    workflow = (Path(__file__).resolve().parents[1] /
                ".github" / "workflows" / "videos.yml").read_text()
    assert "max-parallel: 1" in workflow
    assert "Reject combined topics before costly setup" in workflow
