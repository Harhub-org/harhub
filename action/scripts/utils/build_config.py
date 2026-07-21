"""Loads per-app custom build command overrides from config/commands.toml,
so developers don't need to type the same override every time they
trigger a build — it's remembered once, keyed by app_slug.
"""

import tomllib
from pathlib import Path


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