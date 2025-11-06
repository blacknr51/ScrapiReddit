from __future__ import annotations

import json
from pathlib import Path

import scrapi_reddit.core as core
from scrapi_reddit.core import (
    BASE_URL,
    ListingTarget,
    ScrapeOptions,
    derive_filename,
    extract_links,
    rebuild_csv_from_cache,
)


def test_extract_links_parses_permalinks():
    listing_json = {
        "data": {
            "children": [
                {
                    "data": {
                        "id": "abc123",
                        "title": "Hello World",
                        "permalink": "r/test/comments/abc123/hello_world",
                        "created_utc": 1700000000,
                    }
                }
            ]
        }
    }

    links = extract_links(listing_json)

    assert len(links) == 1
    link = links[0]
    assert link["rank"] == 1
    assert link["url"].startswith(BASE_URL)
    assert link["url"].endswith(".json")


def test_derive_filename_includes_rank_and_slug():
    link_info = {
        "rank": 5,
        "id": "xy1",
        "title": "A neat post",
        "created_utc": 1700000000,
        "permalink": "/r/test/comments/xy1/a_neat_post/",
    }
    filename = derive_filename(link_info, post_data=None)

    assert filename.startswith("005_")
    assert filename.endswith(".json")
    assert "A_neat_post" in filename


def test_rebuild_csv_from_cache(tmp_path: Path):
    subreddit = "example"
    target = ListingTarget(
        label="r/example top (day)",
        output_segments=("subreddits", "example", "top_day"),
        url=f"{BASE_URL}/r/{subreddit}/top/.json",
        params={"t": "day"},
        context=subreddit,
    )
    base_dir = target.output_dir(tmp_path)
    posts_dir = base_dir / "post_jsons"
    posts_dir.mkdir(parents=True)

    listing_entry = {
        "kind": "Listing",
        "data": {
            "children": [
                {
                    "data": {
                        "id": "pq1",
                        "title": "Post title",
                        "created_utc": 1700000500,
                        "permalink": "/r/example/comments/pq1/post_title/",
                    }
                }
            ]
        },
    }
    comments_entry = {
        "kind": "Listing",
        "data": {
            "children": [
                {
                    "kind": "t1",
                    "data": {
                        "id": "c1",
                        "parent_id": "t3_pq1",
                        "author": "foo",
                        "body": "Nice",
                        "score": 1,
                        "created_utc": 1700000600,
                        "permalink": "/r/example/comments/pq1/post_title/c1/",
                    },
                }
            ]
        },
    }
    post_json_path = posts_dir / "001_post.json"
    post_json_path.write_text(json.dumps([listing_entry, comments_entry]), encoding="utf-8")

    links_path = base_dir / "links.json"
    links_path.write_text(
        json.dumps(
            [
                {
                    "rank": 1,
                    "id": "pq1",
                    "title": "Post title",
                    "created_utc": 1700000500,
                    "permalink": "/r/example/comments/pq1/post_title/",
                    "url": f"{BASE_URL}/r/example/comments/pq1/post_title/.json",
                }
            ]
        ),
        encoding="utf-8",
    )

    rebuild_csv_from_cache(target, tmp_path)

    posts_csv = (base_dir / "posts.csv").read_text(encoding="utf-8")
    comments_csv = (base_dir / "comments.csv").read_text(encoding="utf-8")

    assert "Post title" in posts_csv
    assert "c1" in comments_csv


def test_scrape_options_enforces_bounds(tmp_path: Path):
    options = ScrapeOptions(
        output_root=tmp_path,
        listing_limit=1000,
        comment_limit=9999,
        delay=0.1,
        time_filter="day",
        output_formats={"json"},
    )

    assert options.listing_limit == 1000
    assert options.comment_limit == 500
    assert options.delay >= 1.0
    assert options.listing_page_size == 100

    unlimited = ScrapeOptions(
        output_root=tmp_path,
        listing_limit=0,
        comment_limit=250,
        delay=2.0,
        time_filter="day",
        output_formats={"json"},
    )

    assert unlimited.listing_limit is None
    assert unlimited.comment_limit == 250

    zero_comment = ScrapeOptions(
        output_root=tmp_path,
        listing_limit=10,
        comment_limit=0,
        delay=2.0,
        time_filter="day",
        output_formats={"json"},
    )

    assert zero_comment.comment_limit == 500


def test_process_listing_resume_skips_fetch(tmp_path: Path, monkeypatch) -> None:
    subreddit = "example"
    target = ListingTarget(
        label="r/example top (day)",
        output_segments=("subreddits", "example", "top_day"),
        url=f"{BASE_URL}/r/{subreddit}/top/.json",
        params={"t": "day"},
        context=subreddit,
    )

    base_dir = target.output_dir(tmp_path)
    posts_dir = base_dir / "post_jsons"
    posts_dir.mkdir(parents=True)

    listing_json = {
        "data": {
            "children": [
                {
                    "data": {
                        "id": "pq1",
                        "title": "Post title",
                        "created_utc": 1700000500,
                        "permalink": "/r/example/comments/pq1/post_title/",
                    }
                }
            ],
            "after": None,
        }
    }

    post_json = [
        {
            "data": {
                "children": [
                    {
                        "data": {
                            "id": "pq1",
                            "title": "Post title",
                            "created_utc": 1700000500,
                            "permalink": "/r/example/comments/pq1/post_title/",
                        }
                    }
                ]
            }
        },
        {
            "data": {"children": []}
        },
    ]

    cached_path = posts_dir / "001_pq1_cached.json"
    cached_path.write_text(json.dumps(post_json), encoding="utf-8")

    responses = [listing_json]

    def fake_fetch_json(session, url, *, params=None, retries=3, backoff=1.0):  # noqa: D401
        assert responses, "Unexpected additional fetch call"
        return responses.pop(0)

    monkeypatch.setattr(core, "fetch_json", fake_fetch_json)

    sleeps: list[float] = []
    monkeypatch.setattr(core.time, "sleep", lambda seconds: sleeps.append(seconds))

    options = ScrapeOptions(
        output_root=tmp_path,
        listing_limit=10,
        comment_limit=250,
        delay=1.0,
        time_filter="day",
        output_formats={"json"},
        fetch_comments=True,
        resume=True,
    )

    core.process_listing(target, session=object(), options=options)

    assert responses == []
    # Only the post delay should run (no rate limit waits, no fetch delays)
    assert sleeps == []


def test_process_listing_rate_limit_retries(tmp_path: Path, monkeypatch) -> None:
    subreddit = "example"
    target = ListingTarget(
        label="r/example hot",
        output_segments=("subreddits", "example", "hot"),
        url=f"{BASE_URL}/r/{subreddit}/hot/.json",
        context=subreddit,
    )

    base_dir = target.output_dir(tmp_path)
    (base_dir / "post_jsons").mkdir(parents=True)

    listing_json = {
        "data": {
            "children": [
                {
                    "data": {
                        "id": "pq1",
                        "title": "Post title",
                        "created_utc": 1700000500,
                        "permalink": "/r/example/comments/pq1/post_title/",
                    }
                }
            ],
            "after": None,
        }
    }

    post_json = [
        {
            "data": {
                "children": [
                    {
                        "data": {
                            "id": "pq1",
                            "title": "Post title",
                            "created_utc": 1700000500,
                            "permalink": "/r/example/comments/pq1/post_title/",
                        }
                    }
                ]
            }
        },
        {
            "data": {"children": []}
        },
    ]

    call_state = {"count": 0}

    def fake_fetch_json(session, url, *, params=None, retries=3, backoff=1.0):  # noqa: D401
        if "hot" in url and call_state["count"] == 0:
            call_state["count"] += 1
            return listing_json
        # Subsequent calls are for the post JSON
        post_call = call_state.setdefault("post_calls", 0)
        if post_call == 0:
            call_state["post_calls"] = 1
            raise RuntimeError("HTTP 429 Too Many Requests")
        if post_call == 1:
            call_state["post_calls"] = 2
            raise RuntimeError("429 second wave")
        return post_json

    monkeypatch.setattr(core, "fetch_json", fake_fetch_json)

    sleeps: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(core.time, "sleep", fake_sleep)

    options = ScrapeOptions(
        output_root=tmp_path,
        listing_limit=10,
        comment_limit=250,
        delay=0.1,
        time_filter="day",
        output_formats={"json"},
        fetch_comments=True,
    )

    core.process_listing(target, session=object(), options=options)

    # First rate limit should wait 60s, second should wait 120s before succeeding
    assert sleeps[:2] == [60, 120]
