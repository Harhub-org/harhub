"""Generate (or update) metadata.json for a Harhub-enabled repository.

Idempotent: re-running with the same inputs produces byte-identical output,
and re-running with a new version appends/updates that version's entry
without disturbing previous versions.
"""

import json
from pathlib import Path
from datetime import datetime, timezone


def load_existing(metadata_path: Path) -> dict:
    if metadata_path.exists():
        with open(metadata_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"schema_version": 1, "releases": []}


def build_metadata(
    metadata_path: Path,
    repo_owner: str,
    repo_name: str,
    version: str,
    assets: list[dict],
    asset_urls: dict[str, str],
) -> dict:
    metadata = load_existing(metadata_path)
    metadata["repo"] = f"{repo_owner}/{repo_name}"
    metadata["updated_at"] = datetime.now(timezone.utc).isoformat()

    release_entry = {
        "version": version,
        "published_at": datetime.now(timezone.utc).isoformat(),
        "assets": [
            {
                "file_name": a["file_name"],
                "platform": a["platform"],
                "arch": a["arch"],
                "size_bytes": a["size_bytes"],
                "sha256": a["sha256"],
                "url": asset_urls.get(a["file_name"], ""),
            }
            for a in assets
        ],
    }

    existing_releases = [r for r in metadata["releases"] if r["version"] != version]
    existing_releases.append(release_entry)
    existing_releases.sort(key=lambda r: r["published_at"], reverse=True)
    metadata["releases"] = existing_releases

    return metadata


def write_metadata(metadata_path: Path, metadata: dict) -> bool:
    """Writes metadata.json. Returns True if the file content changed."""
    new_content = json.dumps(metadata, indent=2, ensure_ascii=False) + "\n"

    if metadata_path.exists():
        old_content = metadata_path.read_text(encoding="utf-8")
        if old_content == new_content:
            return False

    metadata_path.write_text(new_content, encoding="utf-8")
    return True