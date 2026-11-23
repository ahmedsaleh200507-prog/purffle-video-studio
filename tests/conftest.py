import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))


def write_piper_report(directory, language='de'):
    """Explicit mock provenance for tests of later output gates, no real speech."""
    import json
    from local_voice import provenance
    info=provenance(language)
    target=Path(directory)/'mock-voice-report.json'
    target.write_text(json.dumps({'state':'ready','engine':'piper','voice':info['model'],
                                  'timing':'aligned','provenance':info}))
    return target
