"""One bounded live query per eligible provider; no downloads or secret export."""
import json
from pathlib import Path
from video_sources import ProviderRegistry, JsonClient, STATIC_CATALOGS


def main():
    registry = ProviderRegistry(client=JsonClient(ttl=0))  # Health means a fresh HTTP request, not yesterday's cache.
    results = []
    for provider in registry.health():
        name = provider['provider']
        if not provider['enabled']:
            results.append({**provider, 'live_test': 'skipped'})
            print(f"[SOURCE HEALTH] {name}: skipped ({provider['reason']})", flush=True)
            continue
        candidates = registry.search(name, 'ocean waves')
        event = registry.events[-1]
        results.append({'provider': name, 'live_test': 'catalog_only' if name in STATIC_CATALOGS else event['status'],
                        'candidate_count': len(candidates), 'detail': event['detail'],
                        'cache': 'bypassed', 'scope': ('static manifest filter; no remote API request' if name in STATIC_CATALOGS else 'fresh HTTP search and license metadata only; not download/FFprobe/scene/render')})
    target = Path('finished/provider-health.json')
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(results, indent=2), encoding='utf-8')
    # This diagnostic is not a production-success signal; scene/render errors
    # still fail batch.py. A missing optional provider must not block other ones.
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
