# Error Handling & Edge Cases

Scrapi Reddit is designed to survive intermittent network failures while keeping artifacts consistent. Use this guide to understand how the tool reacts to common issues and how to recover.

## Network & Rate Limits

- Listing and post fetches retry with exponential backoff (60s, 120s, 240s by default).
- After exhausting retries, the exception bubbles up and the current target is marked as failed in CLI output.
- Resume runs (`--continue` or `ScrapeOptions.resume=True`) skip completed `post_jsons`, minimizing rework after partial failures.

## Missing Artifacts

- `rebuild_csv_from_cache` requires `post_jsons/` and `links.json`. If either is absent, a `FileNotFoundError` is raised. Re-run the original scrape or remove the incomplete directory.
- Media manifests (`media_manifest.json`) are optional. When missing, the downloader repopulates them on the next run.

## Output Conflicts

- The tool creates directories as needed. Lack of write permissions raises `OSError` with the offending path.
- Existing CSV files are overwritten atomically: they are written to a temporary file before being replaced, reducing race-condition risk.

## Threaded Comments & Depth

- Comment depth is calculated during flattening. Malformed Reddit data (missing parents) results in `depth=0`, but the row remains in the export so you can inspect the anomaly.

## NSFW & Restricted Content

- Search endpoints hide NSFW results unless `include_over_18=on` or the wizard/config equivalent is set. If the API still redacts content, ensure your account (or network) is allowed to view NSFW data.

## Parsing Search Parameters

- `build_search_target` validates sort orders, time filters, and result types. Unsupported values raise `ValueError` before any network request is made.
- Using `type = "all"` or `*` in configs intentionally disables the search type filter, allowing multi-type responses.

## Suggested Recovery Patterns

1. **Transient HTTP Errors:** rerun with `--continue` to avoid re-downloading successful posts.
2. **Schema Update:** call `scrapi-reddit --rebuild-from-json` after updating CSV columns or data cleaning routines.
3. **Media Failures:** rerun with `--download-media` and `--continue`; missing files are attempted again while existing ones are skipped.
