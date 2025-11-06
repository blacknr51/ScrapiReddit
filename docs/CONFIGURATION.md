# Configuration & Interactive Wizard

Scrapi Reddit accepts a TOML configuration file so you can keep common options in version control. You can also launch an interactive wizard to build a scrape plan without memorizing flags.

## TOML Configuration

Create a file (e.g. `scrape.toml`) with keys matching CLI option names. Any flag absent from the CLI call will fall back to the value provided in the file.

```toml
# scrape.toml
subreddits = ["python", "learnpython"]
subreddit_sorts = "top,hot"
subreddit_top_times = "day,week"
limit = 250
fetch_comments = true
comment_limit = 250
output_format = "both"
search_queries = ["asyncio"]
search_types = ["post", "comment"]
search_sort = "new"
search_time = "week"
search_subreddit = "python"
search_include_over_18 = false
```

Usage:

```powershell
scrapi-reddit --config scrape.toml
```

Rules:
- CLI flags always win. Values from the config apply only when the CLI uses its default.
- Boolean options use `true` / `false`.
- List-based flags (like `--user` or `--search`) accept TOML arrays.
- Paths (`output_dir`, `post_url`, etc.) should be written as strings.

## Interactive Wizard

Enable the guided prompt with `--wizard`:

```powershell
scrapi-reddit --wizard
```

The wizard walks through:
1. Selecting a scrape mode (subreddit listings or keyword search).
2. Entering subreddits or keywords.
3. Choosing limits, comment fetching, media downloading, and output formats.
4. Optionally saving the answers to a TOML file for reuse.

Wizard responses populate the same configuration pipeline as a TOML file, so you can mix-and-match: run `--wizard` once, save the config, and call `scrapi-reddit --config saved.toml` thereafter.
