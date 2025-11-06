from __future__ import annotations

from pathlib import Path

import scrapi_reddit.cli as cli


def test_parse_args_reads_config(tmp_path: Path) -> None:
    config_path = tmp_path / "scrape.toml"
    config_path.write_text(
        "\n".join(
            [
                "limit = 42",
                "fetch_comments = true",
                "search_queries = [\"python\"]",
                "search_types = [\"post\", \"comment\"]",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    args = cli.parse_args(["--config", str(config_path)])

    assert args.limit == 42
    assert args.fetch_comments is True
    assert args.search_queries == ["python"]
    assert cli._parse_csv(args.search_types) == ["post", "comment"]


def test_parse_args_cli_overrides_config(tmp_path: Path) -> None:
    config_path = tmp_path / "override.toml"
    config_path.write_text("limit = 88\n", encoding="utf-8")

    args = cli.parse_args(["--config", str(config_path), "--limit", "30"])

    assert args.limit == 30


def test_parse_csv_accepts_sequence() -> None:
    values = cli._parse_csv(["gif", "mp4", ""])  # blank entries ignored
    assert values == ["gif", "mp4"]
