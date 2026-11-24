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
            # Return complete provider lists. StrictVisuals must rank ALL
            # candidates before imposing its download limit: a relevant fifth
            # result can outrank four superficially similar first results.
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


def discover_portrait_first(registry, sources, queries, deadline, deferred, *, workers=4):
    """Across the available providers: portrait first, unknown size next,
    landscape/square last. Reserve a bounded window for fallback downloads.
    Search is shared; no duplicate API searches just to change orientation.
    """
    start=time.monotonic()
    budget=max(0.,deadline-start)
    portrait_deadline=start+budget*.58
    unknown_deadline=start+budget*.75
    unknown=[]
    for source,candidates in discover(registry,sources,queries,portrait_deadline,workers=workers):
        vertical=[]
        for item in candidates:
            w,h=int(item.width or 0),int(item.height or 0)
            if w<=0 or h<=0:
                unknown.append((source,item))
            elif h>w:
                vertical.append(item)
            else:
                deferred.append((source,item))
        if vertical:
            yield source,vertical,"portrait",portrait_deadline
    # Unknown metadata must not be assumed to mean landscape. Check the
    # downloaded file before letting it enter the landscape fallback.
    for source in dict.fromkeys(src for src,_ in unknown):
        yield source,[item for src,item in unknown if src==source],"unknown_orientation",unknown_deadline
    # Measured nonportrait candidates discovered during earlier phases
    # can also be appended by the caller. Keep all candidates unique.
    for source in dict.fromkeys(src for src,_ in deferred):
        seen=set()
        items=[]
        for src,item in deferred:
            if src==source and item.key not in seen:
                seen.add(item.key)
                items.append(item)
        if items:
            yield source,items,"landscape_fallback",deadline
