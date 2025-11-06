"""Command line entry point for the Scrapi Reddit scraper."""
from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence
from urllib.parse import parse_qsl, urlsplit

try:  # pragma: no cover - dependency import paths
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    try:
        import tomli as tomllib  # type: ignore[assignment]
    except ModuleNotFoundError:  # pragma: no cover
        tomllib = None  # type: ignore[assignment]

from .core import (
    BASE_URL,
    DEFAULT_USER_AGENT,
    build_search_target,
    ListingTarget,
    PostTarget,
    ScrapeOptions,
    build_session,
    process_listing,
    process_post,
    rebuild_csv_from_cache,
    shorten_component,
    normalize_media_filter_tokens,
)


def _default_output_root() -> Path:
    env_override = os.environ.get("SCRAPI_REDDIT_OUTPUT_DIR")
    if env_override:
        return Path(env_override).expanduser().resolve()
    return Path.cwd() / "scrapi_reddit_data"


def _resolve_subreddits(args_subreddits: Sequence[str], prompt: bool) -> List[str]:
    if args_subreddits:
        return [name.strip() for name in args_subreddits if name.strip()]
    if prompt:
        raw = input("Enter subreddit names (comma-separated): ").strip()
        return [name.strip() for name in raw.split(",") if name.strip()]
    return []


def _parse_csv(
    value: str | Sequence[str] | None,
    *,
    default: str | Sequence[str] | None = None,
) -> List[str]:
    raw = value if value is not None else default
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        items = raw.split(",")
    elif isinstance(raw, Sequence):
        items = raw
    else:
        raise SystemExit("Expected string or sequence when parsing comma-separated values.")
    result: List[str] = []
    for item in items:
        trimmed = str(item).strip()
        if trimmed:
            result.append(trimmed)
    return result


def _validate_choices(values: List[str], allowed: set[str], option_name: str) -> None:
    invalid = [v for v in values if v not in allowed]
    if invalid:
        allowed_list = ", ".join(sorted(allowed))
        raise SystemExit(f"Invalid value(s) for {option_name}: {invalid}. Allowed: {allowed_list}")


def _slugify(text: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", text.strip())
    return slug or "item"


_PATH_FIELDS = {"output_dir"}
_LIST_FIELDS = {
    "subreddits",
    "users",
    "listing_url",
    "post_url",
    "search_queries",
    "search_types",
    "popular_sorts",
    "popular_top_times",
    "popular_geo",
    "popular_geo_sorts",
    "subreddit_sorts",
    "subreddit_top_times",
    "user_sections",
    "user_sorts",
}


def _prepare_config_value(key: str, value: Any) -> Any:
    if value is None:
        return None
    if key in _PATH_FIELDS and isinstance(value, str):
        return Path(value).expanduser().resolve()
    if key in _LIST_FIELDS and isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    return value


def _load_config_data(path: Path) -> Dict[str, Any]:
    if tomllib is None:
        raise SystemExit("TOML support requires Python 3.11+ (or install tomli).")
    try:
        with path.expanduser().open("rb") as fp:
            data = tomllib.load(fp)
    except FileNotFoundError as exc:  # pragma: no cover - user error path
        raise SystemExit(f"Configuration file not found: {path}") from exc
    if not isinstance(data, dict):
        raise SystemExit("Configuration file must contain a TOML table at the root.")
    return {key: _prepare_config_value(key, value) for key, value in data.items()}


def _update_namespace(
    args: argparse.Namespace,
    data: Dict[str, Any],
    *,
    defaults: argparse.Namespace | None = None,
    only_if_default: bool = False,
) -> None:
    for key, value in data.items():
        if value is None or not hasattr(args, key):
            continue
        if only_if_default and defaults is not None:
            if getattr(args, key) != getattr(defaults, key, None):
                continue
        setattr(args, key, value)


def _toml_repr(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, (list, tuple)):
        items = ", ".join(_toml_repr(item) for item in value)
        return f"[{items}]"
    raise ValueError(f"Unsupported config value type: {type(value)!r}")


def _dump_toml_lines(data: Dict[str, Any]) -> str:
    lines: List[str] = []
    for key in sorted(data.keys()):
        value = data[key]
        if value is None:
            continue
        lines.append(f"{key} = {_toml_repr(value)}")
    return "\n".join(lines) + ("\n" if lines else "")


def _prompt_bool(prompt: str, default: bool = False) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    while True:
        raw = input(f"{prompt} {suffix}: ").strip().lower()
        if not raw:
            return default
        if raw in {"y", "yes"}:
            return True
        if raw in {"n", "no"}:
            return False
        print("Please enter 'y' or 'n'.")


def _prompt_comma_list(prompt: str) -> List[str]:
    raw = input(f"{prompt}: ").strip()
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _prompt_choice(prompt: str, choices: List[str], default: str) -> str:
    choice_str = ", ".join(choices)
    default_lower = default.lower()
    while True:
        raw = input(f"{prompt} ({choice_str}) [default: {default_lower}]: ").strip().lower()
        if not raw:
            return default_lower
        if raw in choices:
            return raw
        print(f"Choose one of: {choice_str}.")


def _prompt_int(prompt: str, default: int | None = None, minimum: int = 1, maximum: int | None = None) -> int:
    while True:
        raw = input(f"{prompt}{' [default: ' + str(default) + ']' if default is not None else ''}: ").strip()
        if not raw and default is not None:
            return default
        try:
            value = int(raw)
        except ValueError:
            print("Enter a valid integer.")
            continue
        if value < minimum:
            print(f"Value must be >= {minimum}.")
            continue
        if maximum is not None and value > maximum:
            print(f"Value must be <= {maximum}.")
            continue
        return value


def _run_wizard() -> Dict[str, Any]:
    print("Scrapi Reddit Wizard\n=====================")
    print("This guided mode will collect the most common options and build a scrape configuration.\n")

    mode = _prompt_choice("Choose scrape mode", ["listing", "search"], default="listing")
    answers: Dict[str, Any] = {}

    if mode == "listing":
        subreddits = _prompt_comma_list("Enter subreddit names (comma-separated)")
        answers["subreddits"] = subreddits
        sorts = _prompt_comma_list("Listing sorts (comma, e.g. top,hot)") or ["top"]
        answers["subreddit_sorts"] = ",".join(sorts)
        if "top" in [s.lower() for s in sorts]:
            top_times = _prompt_comma_list("Time filters for 'top' (hour,day,week,month,year,all)")
            if top_times:
                answers["subreddit_top_times"] = ",".join(top_times)
        if _prompt_bool("Should I include the front page?", False):
            answers["frontpage"] = True
        if _prompt_bool("Include r/all?", False):
            answers["include_r_all"] = True
        if _prompt_bool("Include r/popular listings?", False):
            answers["popular"] = True
    else:
        query = input("Enter search keywords: ").strip()
        if not query:
            raise SystemExit("Search mode requires a non-empty query.")
        answers["search_queries"] = [query]
        types = _prompt_comma_list("Search types (post,comment,sr,user,media)")
        if types:
            answers["search_types"] = types
        sort = _prompt_choice("Search sort", ["relevance", "hot", "top", "new", "comments"], default="relevance")
        answers["search_sort"] = sort
        time_filter = _prompt_choice("Search time filter", ["all", "day", "week", "month", "year"], default="all")
        answers["search_time"] = time_filter
        sub = input("Restrict to subreddit (leave blank for site-wide): ").strip()
        if sub:
            answers["search_subreddit"] = sub
            answers["search_restrict_sr"] = _prompt_bool("Restrict results to that subreddit?", True)
        answers["search_include_over_18"] = _prompt_bool("Include over_18 results?", False)

    answers["limit"] = _prompt_int("Listing/search limit (1-100)", default=100, minimum=1, maximum=100)
    answers["fetch_comments"] = _prompt_bool("Fetch comments for every post?", True)
    answers["comment_limit"] = _prompt_int("Comment limit per post (max 500)", default=250, minimum=1, maximum=500)
    answers["download_media"] = _prompt_bool("Download media attachments?", False)
    media_filter = input("Media filters (comma-separated, blank for all allowed): ").strip()
    if media_filter:
        answers["media_filter"] = media_filter
    output_choice = _prompt_choice("Output format", ["json", "csv", "both"], default="json")
    answers["output_format"] = output_choice

    if _prompt_bool("Save these answers to a TOML file for reuse?", False):
        path_str = input("Config file path [default: scrape.toml]: ").strip() or "scrape.toml"
        path = Path(path_str).expanduser()
        with path.open("w", encoding="utf-8") as fp:
            fp.write(_dump_toml_lines({k: v for k, v in answers.items() if v}))
        print(f"Saved configuration to {path}.")

    return answers

def _target_from_url(url: str) -> ListingTarget:
    parsed = urlsplit(url)
    if not parsed.scheme or not parsed.netloc:
        raise SystemExit(f"Listing URL must be absolute (including https://): {url}")
    base_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path or '/'}"
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    slug_source = parsed.netloc + (parsed.path or "/")
    if parsed.query:
        slug_source += "?" + parsed.query
    slug = shorten_component(_slugify(slug_source), 80)
    return ListingTarget(
        label=f"custom {parsed.netloc}{parsed.path}",
        output_segments=("custom", slug),
        url=base_url,
        params=params,
        context="custom",
    )


def _post_target_from_url(url: str) -> PostTarget:
    parsed = urlsplit(url)
    if not parsed.scheme or not parsed.netloc:
        raise SystemExit(f"Post URL must be absolute (including https://): {url}")

    path = parsed.path or "/"
    segments = [segment for segment in path.split("/") if segment]

    context = parsed.netloc
    if segments and segments[0].lower() == "r" and len(segments) >= 2:
        context = f"r/{segments[1]}"
    elif segments and segments[0].lower() in {"u", "user"} and len(segments) >= 2:
        context = f"u/{segments[1]}"

    post_id: str | None = None
    try:
        comments_index = next(i for i, segment in enumerate(segments) if segment.lower() == "comments")
    except StopIteration:
        comments_index = -1
    if comments_index != -1 and len(segments) > comments_index + 1:
        post_id = segments[comments_index + 1]

    slug_source_parts: List[str] = []
    if post_id:
        slug_source_parts.append(post_id)
    if segments:
        slug_source_parts.append(segments[-1])
    if not slug_source_parts:
        slug_source_parts.append(parsed.netloc)
    slug_source = "-".join(slug_source_parts)
    slug = shorten_component(_slugify(slug_source), 80)

    json_path = path
    if not json_path.endswith("/"):
        json_path += "/"
    if not json_path.endswith(".json"):
        json_path += ".json"

    params = dict(parse_qsl(parsed.query, keep_blank_values=True))

    label = f"post {context}"
    context_slug = shorten_component(_slugify(context or parsed.netloc), 40)

    url_json = f"{parsed.scheme}://{parsed.netloc}{json_path}"

    return PostTarget(
        label=label,
        output_segments=("posts", context_slug, slug),
        url=url_json,
        params=params,
        context=context,
    )


def _build_targets(
    subreddits: List[str],
    *,
    subreddit_sorts: List[str],
    subreddit_top_times: List[str],
    include_frontpage: bool,
    include_r_all: bool,
    include_popular: bool,
    popular_sorts: List[str],
    popular_top_times: List[str],
    popular_geo: List[str],
    popular_geo_sorts: List[str],
    users: List[str],
    user_sections: List[str],
    user_sorts: List[str],
    listing_urls: List[str],
) -> List[ListingTarget]:
    targets: List[ListingTarget] = []

    allowed_subreddit_sorts = {"top", "best", "hot", "new", "rising"}
    _validate_choices(subreddit_sorts, allowed_subreddit_sorts, "--subreddit-sorts")
    allowed_time_filters = {"hour", "day", "week", "month", "year", "all"}
    if "top" in subreddit_sorts:
        _validate_choices(subreddit_top_times, allowed_time_filters, "--subreddit-top-times")

    for subreddit in subreddits:
        slug_name = _slugify(subreddit)
        for sort in subreddit_sorts:
            if sort == "top":
                for timeframe in subreddit_top_times:
                    targets.append(
                        ListingTarget(
                            label=f"r/{subreddit} top ({timeframe})",
                            output_segments=(
                                "subreddits",
                                slug_name,
                                f"top_{_slugify(timeframe)}",
                            ),
                            url=f"{BASE_URL}/r/{subreddit}/top/.json",
                            params={"t": timeframe},
                            context=subreddit,
                        )
                    )
            else:
                targets.append(
                    ListingTarget(
                        label=f"r/{subreddit} {sort}",
                        output_segments=("subreddits", slug_name, sort),
                        url=f"{BASE_URL}/r/{subreddit}/{sort}/.json",
                        context=subreddit,
                    )
                )

    if include_frontpage:
        targets.append(
            ListingTarget(
                label="reddit.com front page",
                output_segments=("frontpage", "default"),
                url=f"{BASE_URL}/.json",
                context="frontpage",
            )
        )

    if include_r_all:
        targets.append(
            ListingTarget(
                label="r/all",
                output_segments=("all", "default"),
                url=f"{BASE_URL}/r/all/.json",
                context="all",
            )
        )

    allowed_popular_sorts = {"best", "hot", "new", "top", "rising"}
    _validate_choices(popular_sorts, allowed_popular_sorts, "--popular-sorts")
    if include_popular:
        for sort in popular_sorts:
            if sort == "top":
                _validate_choices(popular_top_times, allowed_time_filters, "--popular-top-times")
                for timeframe in popular_top_times:
                    targets.append(
                        ListingTarget(
                            label=f"r/popular top ({timeframe})",
                            output_segments=("popular", "top", _slugify(timeframe)),
                            url=f"{BASE_URL}/r/popular/top/.json",
                            params={"t": timeframe},
                            context="popular",
                        )
                    )
            else:
                targets.append(
                    ListingTarget(
                        label=f"r/popular {sort}",
                        output_segments=("popular", sort),
                        url=f"{BASE_URL}/r/popular/{sort}/.json",
                        context="popular",
                    )
                )

    if popular_geo:
        allowed_popular_geo_sorts = {"best", "hot", "new", "top", "rising"}
        _validate_choices(popular_geo_sorts, allowed_popular_geo_sorts, "--popular-geo-sorts")
        for geo in popular_geo:
            code = geo.lower()
            geo_slug = _slugify(code)
            for sort in popular_geo_sorts:
                if sort == "top":
                    _validate_choices(popular_top_times, allowed_time_filters, "--popular-top-times")
                    for timeframe in popular_top_times:
                        targets.append(
                            ListingTarget(
                                label=f"r/popular top (geo={code}, {timeframe})",
                                output_segments=(
                                    "popular",
                                    "geo",
                                    geo_slug,
                                    "top",
                                    _slugify(timeframe),
                                ),
                                url=f"{BASE_URL}/r/popular/top/.json",
                                params={"geo_filter": code, "t": timeframe},
                                context="popular",
                            )
                        )
                else:
                    targets.append(
                        ListingTarget(
                            label=f"r/popular {sort} (geo={code})",
                            output_segments=("popular", "geo", geo_slug, sort),
                            url=f"{BASE_URL}/r/popular/{sort}/.json",
                            params={"geo_filter": code},
                            context="popular",
                        )
                    )

    allowed_user_sections = {"overview", "submitted", "comments"}
    _validate_choices(user_sections, allowed_user_sections, "--user-sections")
    allowed_user_sorts = {"new", "hot", "top", "best"}
    _validate_choices(user_sorts, allowed_user_sorts, "--user-sorts")
    for user in users:
        slug_user = _slugify(user)
        for section in user_sections:
            if section == "overview":
                path = f"/user/{user}/.json"
            else:
                path = f"/user/{user}/{section}/.json"
            for sort in user_sorts:
                targets.append(
                    ListingTarget(
                        label=f"u/{user} {section} ({sort})",
                        output_segments=("users", slug_user, section, sort),
                        url=f"{BASE_URL}{path}",
                        params={"sort": sort},
                        context=f"u/{user}",
                    )
                )

    for url in listing_urls:
        targets.append(_target_from_url(url))

    return targets


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    raw_argv = list(argv) if argv is not None else sys.argv[1:]

    config_parser = argparse.ArgumentParser(add_help=False)
    config_parser.add_argument("--config", type=Path)
    config_ns, remaining = config_parser.parse_known_args(raw_argv)

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
        help=(
            "Maximum number of items to fetch per listing (total). Values above 100 trigger paginated "
            "fetches; use 0 for no explicit cap (default: 100)."
        ),
    )
    parser.add_argument(
        "--comment-limit",
        type=int,
        default=250,
        help="Comments per post request (default: 250, max: 500).",
    )
    parser.add_argument(
        "--fetch-comments",
        action="store_true",
        help="Fetch comments for listing posts (default: disabled to reduce API calls).",
    )
    parser.add_argument(
        "--download-media",
        action="store_true",
        help="Download linked images, GIFs, and videos for each scraped post.",
    )
    parser.add_argument(
        "--media-filter",
        default=None,
        help=(
            "Comma-separated list of media categories or extensions to download when --download-media is set. "
            "Supported categories: video, image, animated; extensions: mp4, webm, gif, jpg, png, etc."
        ),
    )
    parser.add_argument(
        "--continue",
        dest="resume",
        action="store_true",
        help=(
            "Resume a previous run by reusing cached post_jsons files when present, skipping redundant fetches."
        ),
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=3.0,
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
        "--subreddit-sorts",
        default="top",
        help=(
            "Comma-separated listing sorts for subreddit targets (choices: best, hot, new, rising, top)."
        ),
    )
    parser.add_argument(
        "--subreddit-top-times",
        default=None,
        help=(
            "Comma-separated time filters for subreddit 'top' listings (choices: hour, day, week, month, year, all)."
        ),
    )
    parser.add_argument(
        "--search",
        dest="search_queries",
        action="append",
        default=[],
        help="Search query string to fetch from search.json. Provide multiple times for multiple queries.",
    )
    parser.add_argument(
        "--search-types",
        default=None,
        help=(
            "Comma-separated search result types to request (choices: post, link, comment, sr, user, media)."
        ),
    )
    parser.add_argument(
        "--search-sort",
        default="relevance",
        choices=["relevance", "hot", "top", "new", "comments"],
        help="Sort order for search results (default: relevance).",
    )
    parser.add_argument(
        "--search-time",
        default="all",
        choices=["all", "day", "week", "month", "year"],
        help="Time filter for search results (default: all).",
    )
    parser.add_argument(
        "--search-subreddit",
        default=None,
        help="Limit search to a specific subreddit (name without the r/ prefix).",
    )
    parser.add_argument(
        "--search-restrict-sr",
        action="store_true",
        help="Force restrict_sr=on when using --search-subreddit to stay inside that community.",
    )
    parser.add_argument(
        "--search-include-over-18",
        action="store_true",
        help="Include results flagged as over_18 (NSFW).",
    )
    parser.add_argument(
        "--search-limit",
        type=int,
        default=100,
        help="Maximum results per search request (1-100, default: 100).",
    )
    parser.add_argument(
        "--search-after",
        default=None,
        help="After cursor for resuming a search (optional).",
    )
    parser.add_argument(
        "--search-before",
        default=None,
        help="Before cursor for reverse pagination of a search (optional).",
    )
    parser.add_argument(
        "--wizard",
        action="store_true",
        help="Launch an interactive wizard to collect common settings.",
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
        "--frontpage",
        action="store_true",
        help="Include the reddit.com front page (.json) listing in the scrape run.",
    )
    parser.add_argument(
        "--include-r-all",
        action="store_true",
        help="Include the r/all listing in the scrape run.",
    )
    parser.add_argument(
        "--popular",
        action="store_true",
        help="Include r/popular listings using the sorts configured via --popular-sorts.",
    )
    parser.add_argument(
        "--popular-sorts",
        default="best,hot,new,top,rising",
        help=(
            "Comma-separated sorts for r/popular when --popular is provided (choices: best, hot, new, top, rising)."
        ),
    )
    parser.add_argument(
        "--popular-top-times",
        default=None,
        help=(
            "Comma-separated time filters for r/popular 'top' listings (choices: hour, day, week, month, year, all)."
        ),
    )
    parser.add_argument(
        "--popular-geo",
        default="",
        help=(
            "Comma-separated geo_filter codes for r/popular/best (e.g. us, ar, au)."
        ),
    )
    parser.add_argument(
        "--popular-geo-sorts",
        default="best,hot,new,top,rising",
        help=(
            "Comma-separated sorts for geo-filtered r/popular listings (choices: best, hot, new, top, rising)."
        ),
    )
    parser.add_argument(
        "--user",
        dest="users",
        action="append",
        default=[],
        help="Reddit username to scrape (overview, submitted, comments). Provide multiple times for multiple users.",
    )
    parser.add_argument(
        "--user-sections",
        default="overview,submitted,comments",
        help="Comma-separated user sections to scrape (choices: overview, submitted, comments).",
    )
    parser.add_argument(
        "--user-sorts",
        default="new,hot,top",
        help="Comma-separated sorts for user listings (choices: new, hot, top, best).",
    )
    parser.add_argument(
        "--listing-url",
        action="append",
        default=[],
        help="Additional listing JSON URL to scrape. Provide multiple times for multiple endpoints.",
    )
    parser.add_argument(
        "--post-url",
        action="append",
        default=[],
        help="Reddit post permalink to scrape individually (fetches comments). Provide multiple times.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Root directory where scrape artifacts are saved. Defaults to ./scrapi_reddit_data "
            "(override with SCRAPI_REDDIT_OUTPUT_DIR)."
        ),
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
        help="Logging verbosity (default: INFO).",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to a TOML configuration file whose values populate missing CLI options.",
    )

    defaults = parser.parse_args([])
    args = parser.parse_args(remaining)
    args.config = config_ns.config or args.config

    if args.config is not None:
        config_data = _load_config_data(args.config)
        _update_namespace(args, config_data, defaults=defaults, only_if_default=True)

    return args


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    if args.wizard:
        wizard_answers = {
            key: _prepare_config_value(key, value)
            for key, value in _run_wizard().items()
        }
        _update_namespace(args, wizard_answers, only_if_default=False)
    subreddits = _resolve_subreddits(args.subreddits, args.prompt)

    log_level = getattr(logging, args.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        force=True,
    )
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    output_formats: set[str]
    if args.output_format == "both":
        output_formats = {"json", "csv"}
    elif args.output_format == "csv":
        output_formats = {"csv"}
    else:
        output_formats = {"json"}

    output_root = Path(args.output_dir).expanduser().resolve() if args.output_dir else _default_output_root()
    output_root.mkdir(parents=True, exist_ok=True)

    try:
        media_filters = normalize_media_filter_tokens(
            _parse_csv(args.media_filter) if args.media_filter else None
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    options = ScrapeOptions(
        output_root=output_root,
        listing_limit=args.limit,
        comment_limit=args.comment_limit,
        delay=args.delay,
        time_filter=args.time_filter,
        output_formats=output_formats,
        fetch_comments=args.fetch_comments,
        resume=args.resume,
        download_media=args.download_media,
        media_filters=media_filters,
    )

    subreddit_sorts = _parse_csv(args.subreddit_sorts, default="top")
    subreddit_top_times = _parse_csv(
        args.subreddit_top_times, default=args.time_filter
    )
    if "top" in subreddit_sorts and not subreddit_top_times:
        subreddit_top_times = [args.time_filter]

    popular_sorts = _parse_csv(args.popular_sorts)
    popular_geo_sorts = _parse_csv(args.popular_geo_sorts)
    popular_top_times = _parse_csv(args.popular_top_times, default=args.time_filter)
    if ("top" in popular_sorts or "top" in popular_geo_sorts) and not popular_top_times:
        popular_top_times = [args.time_filter]
    if "top" not in popular_sorts and "top" not in popular_geo_sorts:
        popular_top_times = []

    popular_geo = [code for code in _parse_csv(args.popular_geo) if code]
    user_sections = _parse_csv(args.user_sections)
    user_sorts = _parse_csv(args.user_sorts)

    if args.search_restrict_sr and not args.search_subreddit:
        raise SystemExit("--search-restrict-sr requires --search-subreddit")

    search_targets: List[ListingTarget] = []
    search_queries = [query.strip() for query in args.search_queries if query and query.strip()]
    if search_queries:
        search_types = _parse_csv(args.search_types, default="link")
        search_limit = args.search_limit
        if search_limit is not None:
            if search_limit <= 0:
                raise SystemExit("--search-limit must be greater than 0")
            search_limit = max(1, min(search_limit, 100))

        for query in search_queries:
            try:
                target = build_search_target(
                    query,
                    search_types=search_types if search_types else None,
                    sort=args.search_sort,
                    time_filter=args.search_time,
                    subreddit=args.search_subreddit,
                    restrict_to_subreddit=args.search_restrict_sr if args.search_subreddit else None,
                    include_over_18=args.search_include_over_18,
                    limit=search_limit,
                    after=args.search_after,
                    before=args.search_before,
                )
            except ValueError as exc:
                raise SystemExit(str(exc)) from exc
            search_targets.append(target)

    listing_targets = _build_targets(
        subreddits,
        subreddit_sorts=subreddit_sorts,
        subreddit_top_times=subreddit_top_times,
        include_frontpage=args.frontpage,
        include_r_all=args.include_r_all,
        include_popular=args.popular,
        popular_sorts=popular_sorts,
        popular_top_times=popular_top_times,
        popular_geo=popular_geo,
        popular_geo_sorts=popular_geo_sorts,
        users=[name.strip() for name in args.users if name and name.strip()],
        user_sections=user_sections,
        user_sorts=user_sorts,
        listing_urls=args.listing_url,
    )

    listing_targets.extend(search_targets)

    post_urls = [url.strip() for url in args.post_url if url and url.strip()]
    post_targets = [_post_target_from_url(url) for url in post_urls]

    if not listing_targets and not post_targets:
        raise SystemExit(
            "No targets selected. Provide listing targets (subreddits, --popular/--frontpage/--include-r-all, --user, --listing-url) or --post-url."
        )

    if args.rebuild_from_json:
        if post_targets:
            print("Skipping --post-url targets during rebuild; only listings support CSV regeneration.", file=sys.stderr)
        for target in listing_targets:
            try:
                rebuild_csv_from_cache(target, options.output_root)
            except Exception as exc:  # noqa: BLE001 - surface error but continue
                print(f"Failed to rebuild CSV for {target.label}: {exc}", file=sys.stderr)
        return

    session = build_session(args.user_agent, not args.insecure)

    for target in listing_targets:
        try:
            process_listing(target, session=session, options=options)
        except Exception as exc:  # noqa: BLE001 - keep processing other subreddits
            print(f"Failed to process {target.label}: {exc}", file=sys.stderr)

    for target in post_targets:
        try:
            process_post(target, session=session, options=options)
        except Exception as exc:  # noqa: BLE001 - continue processing remaining posts
            print(f"Failed to process {target.label}: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
