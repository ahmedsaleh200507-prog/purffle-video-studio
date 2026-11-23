"""Fair, bounded provider discovery; downloads and neural checks stay sequential."""
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import time


def discover(registry, sources, queries, deadline, *, workers=4):
    sources = list(dict.fromkeys(sources))
    queries = list(dict.fromkeys(q.strip() for q in queries if q.strip()))[:6]
    seen = {source: set() for source in sources}
    pool = ThreadPoolExecutor(max_workers=max(1, min(4, workers)))
    def search(source, query):
        if time.monotonic() >= deadline:
            return []
        client = getattr(registry, 'client', None)
        if hasattr(client, '_context'):
            client._context.deadline = deadline
        return registry.search(source, query)
    try:
        for query in queries:
            if time.monotonic() >= deadline:
                return
            pending = {pool.submit(search, source, query): source for source in sources
                       if source not in getattr(registry, '_circuit', ())}
            while pending:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return
                ready, _ = wait(pending, timeout=remaining, return_when=FIRST_COMPLETED)
                if not ready:
                    return
                # Deterministic provider preference when multiple results are ready.
                for future in sorted(ready, key=lambda f: sources.index(pending[f])):
                    source = pending.pop(future)
                    try:
                        candidates = future.result()
                    except Exception as exc:
                        if hasattr(registry, 'event'):
                            registry.event(source, 'search_exception', query, detail=type(exc).__name__)
                        candidates = []
                    fresh = []
                    for candidate in candidates:
                        if candidate.key not in seen[source]:
                            seen[source].add(candidate.key)
                            fresh.append(candidate)
                    yield source, fresh
    finally:
        # Pending requests never survive the stage. Running HTTP calls observe
        # JsonClient's shared scene deadline and bounded connect/read timeouts.
        pool.shutdown(wait=True, cancel_futures=True)
