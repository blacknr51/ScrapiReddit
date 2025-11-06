# Scrapi Reddit API Reference

This document summarizes the primary classes and functions exposed by the Scrapi Reddit package. Import them from `scrapi_reddit` unless noted otherwise.

## Session & Options

### `build_session(user_agent: str, verify: bool) -> requests.Session`
Creates a preconfigured `requests.Session` with Reddit-friendly headers. Set `verify=False` to bypass TLS validation when testing on restricted networks.

### `ScrapeOptions`
Configuration dataclass passed to `process_listing` / `process_post`.

Key fields:
- `output_root (Path)`: Root directory for all artifacts.
- `listing_limit (int | None)`: Maximum items per listing; `None` means unlimited.
- `comment_limit (int)`: Max comments per post (capped at 500).
- `delay (float)`: Seconds between post fetches; enforced minimum is 1.0.
- `time_filter (str)`: Default timeframe for "top" listings (hour/day/week/month/year/all).
- `output_formats (set[str])`: Any combination of `{"json", "csv"}`.
- `fetch_comments (bool)`: Whether to follow each listing post with a comment pull.
- `resume (bool)`: Reuse cached JSON/media to skip existing work.
- `download_media (bool)`: Save discovered media files under the target's `media/` directory.
- `media_filters (set[str] | None)`: Allowed media tokens (categories or extensions).

### `ListingTarget`
Dataclass describing a listing endpoint (subreddit, search query, front page, etc.). Use helper factories (e.g. `_build_targets` inside the CLI or `build_search_target`) to make instances.

Fields:
- `label`: Human readable name for logs.
- `output_segments`: Tuple mapping to directories inside `output_root`.
- `url`: Fully-qualified Reddit JSON URL to fetch.
- `params`: Default query parameters for the listing.
- `context`: Short identifier (e.g. `python`, `search`).
- `allow_limit`: If `False`, use server-provided `limit` unchanged.

### `PostTarget`
Describes a single post (permalink) JSON endpoint. Useful when you only need a single thread but still want cached JSON/CSV artifacts.

### `build_search_target(...) -> ListingTarget`
Utility for constructing search listings. Accepts keyword text plus optional type filters, sort order, time filter, and subreddit restriction. Returns a `ListingTarget` that plugs into `process_listing`.

## Core Helpers

### `fetch_json(session, url, *, params=None, retries=3, backoff=1.0)`
Fetches a JSON document with retry/backoff on transient failures (rate limits, gateway errors). Raises the original exception after all retries.

### `extract_links(listing_json)`
Pulls the `children` array out of a listing response, yielding normalized link dictionaries with rank, IDs, permalinks, and JSON URLs ready for downstream processing.

### `process_listing(target, session, options)`
Primary worker for listings. Handles pagination, caching, comment fetching, CSV writing, and optional media downloads. Respects `listing_limit`, `delay`, and `resume` options.

### `process_post(target, session, options)`
Processes a single post target. Useful when combining listing data with ad-hoc thread fetches.

### `rebuild_csv_from_cache(target, output_root)`
Recreates `posts.csv` and `comments.csv` from previously cached `post_jsons` plus `links.json`. Handy after adjusting CSV schema or when recovering from interrupted runs.

### `flatten_post_record(...)` / `flatten_comments(...)`
Convert nested JSON structures into flat CSV-ready dictionaries. Used internally but available if you want to roll your own writers.

### `normalize_media_filter_tokens(tokens)`
Parses user-provided media filters (category names or extensions) into canonical tokens used by the downloader.

## Error Handling Expectations

- Network and rate limit failures bubble up after the configured retry attempts. Wrap top-level calls in a try/except block if you need custom recovery.
- File-system operations (`write_csv`, media downloads) create parent directories on demand and raise regular `OSError` if permissions fail.
- `rebuild_csv_from_cache` raises `FileNotFoundError` when cached JSON artifacts are missing. Check `target.output_dir(output_root)` before calling.
- `build_search_target` validates sort/type/time options and raises `ValueError` for unsupported combinations.

## Import Paths

The package exports the most common helpers at the top level:

```python
from scrapi_reddit import (
    build_session,
    build_search_target,
    ListingTarget,
    PostTarget,
    ScrapeOptions,
    process_listing,
    process_post,
    rebuild_csv_from_cache,
)
```

Refer to the source (`scrapi_reddit/core.py`) for advanced internals that are not part of the stable API.
