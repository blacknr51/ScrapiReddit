"""Command line entry point for the Scrapi Reddit scraper."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import List, Sequence

from .core import (
    DEFAULT_USER_AGENT,
    ScrapeOptions,
    build_session,
    process_subreddit,
    rebuild_csv_from_cache,
)


def _default_output_root() -> Path:
    platform = os.name
    if platform == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home()))
        return base / "ScrapiReddit" / "data"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "ScrapiReddit"
    cache_home = os.environ.get("XDG_CACHE_HOME")
    if cache_home:
        return Path(cache_home) / "scrapi_reddit"
    return Path.home() / ".cache" / "scrapi_reddit"


def _resolve_subreddits(args_subreddits: Sequence[str], prompt: bool) -> List[str]:
    if args_subreddits:
        return [name.strip() for name in args_subreddits if name.strip()]
    if prompt:
        raw = input("Enter subreddit names (comma-separated): ").strip()
        return [name.strip() for name in raw.split(",") if name.strip()]
    raise SystemExit("No subreddits provided. Use --prompt for interactive input.")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Scrape Reddit listings for one or more subreddits. Respect Reddit rate limits; "
            "the tool enforces a minimum one-second delay between post requests."
        )
    )
    parser.add_argument(
        "subreddits",
        nargs="*",
        help="Subreddit names (without the r/ prefix).",
    )
    parser.add_argument(
        "--prompt",
        action="store_true",
        help="Prompt interactively for subreddit names when none are provided.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum number of posts to fetch from the listing (default: 100).",
    )
    parser.add_argument(
        "--comment-limit",
        type=int,
        default=500,
        help="Maximum number of comments to retrieve per post (default: 500).",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Delay in seconds between individual post requests (minimum enforced: 1.0).",
    )
    parser.add_argument(
        "--user-agent",
        default=DEFAULT_USER_AGENT,
        help="Custom User-Agent header to send with requests.",
    )
    parser.add_argument(
        "--time-filter",
        choices=["hour", "day", "week", "month", "year", "all"],
        default="day",
        help="Which 'top' timeframe to use (default: day).",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Disable TLS certificate verification (only if you trust the network).",
    )
    parser.add_argument(
        "--rebuild-from-json",
        action="store_true",
        help="Recreate CSV outputs from previously saved JSON files without new network calls.",
    )
    parser.add_argument(
        "--output-format",
        choices=["json", "csv", "both"],
        default="json",
        help="Persist results as JSON files, CSV summaries, or both (default: json).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Root directory where scrape artifacts are saved. Defaults to an OS-specific cache "
            "folder (e.g. %%LOCALAPPDATA%%/ScrapiReddit/data on Windows)."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    subreddits = _resolve_subreddits(args.subreddits, args.prompt)

    output_formats: set[str]
    if args.output_format == "both":
        output_formats = {"json", "csv"}
    elif args.output_format == "csv":
        output_formats = {"csv"}
    else:
        output_formats = {"json"}

    output_root = Path(args.output_dir) if args.output_dir else _default_output_root()
    output_root.mkdir(parents=True, exist_ok=True)

    options = ScrapeOptions(
        output_root=output_root,
        listing_limit=args.limit,
        comment_limit=args.comment_limit,
        delay=args.delay,
        time_filter=args.time_filter,
        output_formats=output_formats,
    )

    if args.rebuild_from_json:
        for subreddit in subreddits:
            try:
                rebuild_csv_from_cache(subreddit, options.output_root)
            except Exception as exc:  # noqa: BLE001 - surface error but continue
                print(f"Failed to rebuild CSV for r/{subreddit}: {exc}", file=sys.stderr)
        return

    session = build_session(args.user_agent, not args.insecure)

    for subreddit in subreddits:
        try:
            process_subreddit(subreddit, session=session, options=options)
        except Exception as exc:  # noqa: BLE001 - keep processing other subreddits
            print(f"Failed to process r/{subreddit}: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
