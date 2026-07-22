"""Shared loader for config/tracked-repos.toml — used by every
harhub-*.yml pipeline (manual publish, build-from-source, scheduled sync)
so every field (repo, branch, visibility, build settings) is sourced
from this one config file, keyed by app_slug.
"""

import tomllib
from pathlib import Path
from urllib.parse import urlparse


def _parse_repo_url(url: str) -> tuple[str, str]:
    path = urlparse(url).path.strip("/")
    parts = path.removesuffix(".git").split("/")
    if len(parts) < 2:
        raise ValueError(f"Invalid GitHub repo URL: {url}")
    return parts[0], parts[1]


def load_all_tracked_repos() -> list[dict]:
    config_path = Path(__file__).resolve().parent.parent.parent / "config" / "tracked-repos.toml"
    if not config_path.exists():
        return []

    with open(config_path, "rb") as f:
        data = tomllib.load(f)

    repos = []
    for entry in data.get("repos", []):
        owner, repo = _parse_repo_url(entry["url"])
        repos.append({
            "owner": owner,
            "repo": repo,
            "url": entry["url"],
            "app_slug": entry["app_slug"],
            "branch": entry.get("branch", f"{entry['app_slug']}-downloads"),
            "visibility": entry.get("visibility", "public"),
            "module_path": entry.get("module_path", ""),
            "build_system": entry.get("build_system", "auto"),
        })
    return repos


def find_tracked_repo(app_slug: str) -> dict | None:
    for entry in load_all_tracked_repos():
        if entry["app_slug"] == app_slug:
            return entry
    return None