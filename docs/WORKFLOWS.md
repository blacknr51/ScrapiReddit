# Sample Workflows

These scenarios illustrate how to combine Scrapi Reddit's CLI and Python API for real-world projects.

## Daily Trending Dashboard

1. Run a scheduled search scrape for your keywords:
   ```powershell
   scrapi-reddit --search "python ai" --search-sort top --search-time day --output-format both --download-media
   ```
2. Point your BI tool (e.g. Power BI, Metabase) at `scrapi_reddit_data/search/python_ai/` and refresh.
3. Use the generated `posts.csv` and `comments.csv` for analytics, while media assets stay under `media/` for manual review.

## Competitive Monitoring

1. Create a TOML config (`monitor.toml`):
   ```toml
   subreddits = ["technology", "gadgets"]
   subreddit_sorts = "top,hot"
   subreddit_top_times = "day,week"
   fetch_comments = true
   download_media = true
   limit = 200
   ```
2. Run the scraper nightly with the config:
   ```powershell
   scrapi-reddit --config monitor.toml
   ```
3. Combine the daily CSV exports into a warehouse table to track sentiment and media trends.

## Research Notebook Integration

1. Use the Python API to fetch targeted threads:
   ```python
   from pathlib import Path
   from scrapi_reddit import (
       build_session,
       build_search_target,
       ScrapeOptions,
       process_listing,
   )

   session = build_session("my-research-bot/0.1", verify=True)

   options = ScrapeOptions(
       output_root=Path("./notebook_runs"),
       listing_limit=150,
       comment_limit=0,
       delay=2.0,
       time_filter="week",
       output_formats={"json", "csv"},
       fetch_comments=True,
       download_media=False,
   )

   target = build_search_target("python asyncio", search_types=["comment"], sort="new", time_filter="week")
   process_listing(target, session=session, options=options)
   ```
2. Load the resulting CSV files directly into pandas for analysis:
   ```python
   import pandas as pd
   comments = pd.read_csv("notebook_runs/search/python_asyncio/types_comment/sort_new/t_week/comments.csv")
   comments.head()
   ```

## Data Recovery

If a long run is interrupted, all cached `post_jsons` remain intact. To rebuild CSVs without re-scraping:

```powershell
scrapi-reddit python --rebuild-from-json --limit 0
```

For targeted rebuilds, loop through selected output directories and invoke `rebuild_csv_from_cache` from the Python API.
