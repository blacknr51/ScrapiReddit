# Scrapi Reddit

Scrapi Reddit is a zero-auth scraper for public Reddit listings. Use it as a Python package or via the bundled CLI to collect posts (and optional flattened CSV summaries) from subreddits, the front page, r/popular, r/all, user profiles, or any arbitrary Reddit listing URL.

## Installation

```bash
pip install -e .
```

## CLI Usage

```bash
python scrapi-reddit.py [subreddits ...] [options]
```

Common scenarios:

- Subreddits with multiple sorts/timeframes:
	```powershell
	python scrapi-reddit.py python MobileLegendsGame --subreddit-sorts top,best,hot,new,rising --subreddit-top-times hour,day,week,month,year,all --output-format both
	```
	- Paginated subreddit grab (fetch 1000 posts total):
		```powershell
		python scrapi-reddit.py python --limit 1000
		```
- Popular listings including geo filters:
	```powershell
	python scrapi-reddit.py --popular --popular-geo us,ar,au,de,jp
	```
- Front page and r/all:
	```powershell
	python scrapi-reddit.py --frontpage --include-r-all --limit 50
	```
- User activity (overview, submissions, comments):
	```powershell
	python scrapi-reddit.py --user CockyNobody_27 --user-sections overview,submitted,comments --user-sorts new,hot,top --limit 100
	```
- Direct listing URLs:
	```powershell
	python scrapi-reddit.py --listing-url https://www.reddit.com/r/popular/best/.json?geo_filter=gb --listing-url https://www.reddit.com/r/all/.json
	```
- Opt-in comment fetching for listing runs:
	```powershell
	python scrapi-reddit.py python --fetch-comments --comment-limit 100 --output-format both
	```
- Single post (including full comment tree):
	```powershell
	python scrapi-reddit.py --post-url https://www.reddit.com/r/python/comments/xyz789/example_post/
	```
- Resume a long scrape after interruption:
	```powershell
	python scrapi-reddit.py python --fetch-comments --continue --output-format both
	```

Artifacts now default to `./scrapi_reddit_data` (or the path in `SCRAPI_REDDIT_OUTPUT_DIR`). Override with `--output-dir` if you prefer another location. Set `--output-format both` to persist CSV summaries alongside the raw JSON.

`--limit` controls the total number of posts fetched per listing (defaults to 100, set `--limit 0` to fetch until the listing exhausts its `after` cursor). Comment requests default to `--comment-limit 250` (max 500 per fetch) and only run when `--fetch-comments` or `--post-url` is provided, keeping the scraper lightweight by default.

## Python API

```python
from pathlib import Path

from scrapi_reddit import (
		ListingTarget,
		PostTarget,
		ScrapeOptions,
		build_session,
		process_listing,
		process_post,
)

session = build_session("my-user-agent", verify=True)
options = ScrapeOptions(
		output_root=Path("./data"),
		listing_limit=100,
		comment_limit=200,
		delay=2.0,
		time_filter="day",
		output_formats={"json", "csv"},
		resume=False,
)

target = ListingTarget(
		label="r/python top (day)",
		output_segments=("subreddits", "python", "top_day"),
		url="https://www.reddit.com/r/python/top/.json",
		params={"t": "day"},
		context="python",
)

process_listing(target, session=session, options=options)

post_target = PostTarget(
	label="example post",
	output_segments=("posts", "python", "xyz789"),
	url="https://www.reddit.com/r/python/comments/xyz789/example_post/.json",
)

process_post(post_target, session=session, options=options)
```

## Testing

```bash
python -m pytest
```
