"""Loads per-app custom build command overrides from config/commands.toml.
Every app_slug referenced here must already exist in
config/tracked-repos.toml — app_slug itself is never re-defined here,
only referenced, so there is a single source of truth for which slugs
are valid.
"""

import sys
import tomllib
from pathlib import Path

from utils.tracked_repos import load_all_tracked_repos


def load_command_override(app_slug: str) -> dict | None:
    config_path = Path(__file__).resolve().parent.parent.parent / "config" / "commands.toml"
    if not config_path.exists():
        return None

    with open(config_path, "rb") as f:
        data = tomllib.load(f)

    for entry in data.get("commands", []):
        if entry.get("app_slug") == app_slug:
            return entry

    return None


def validate_commands_config() -> None:
    """Fails loudly if commands.toml references an app_slug that isn't
    registered in tracked-repos.toml — catches typos/stale entries early
    instead of silently no-op-ing at build time.
    """
    config_path = Path(__file__).resolve().parent.parent.parent / "config" / "commands.toml"
    if not config_path.exists():
        return

    with open(config_path, "rb") as f:
        data = tomllib.load(f)

    known_slugs = {r["app_slug"] for r in load_all_tracked_repos()}

    for entry in data.get("commands", []):
        slug = entry.get("app_slug")
        if slug not in known_slugs:
            print(
                f"::error::config/commands.toml references app_slug '{slug}' "
                f"which is not registered in config/tracked-repos.toml",
                file=sys.stderr,
            )
            sys.exit(1)


if __name__ == "__main__":
    validate_commands_config()
    print("config/commands.toml: all app_slug references are valid.")