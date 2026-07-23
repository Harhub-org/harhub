"""Resolves a Harhub app_slug into its config/tracked-repos.toml entry
and writes repo (owner/repo format, for actions/checkout) and
pinned_version to $GITHUB_OUTPUT.

Usage: python scripts/resolve_repo.py <app_slug>
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils.tracked_repos import find_tracked_repo


def main() -> None:
    if len(sys.argv) < 2:
        print("::error::usage: resolve_repo.py <app_slug>", file=sys.stderr)
        sys.exit(1)

    app_slug = sys.argv[1]
    entry = find_tracked_repo(app_slug)

    if entry is None:
        print(
            f"::error::app_slug '{app_slug}' has no matching entry in config/tracked-repos.toml",
            file=sys.stderr,
        )
        sys.exit(1)

    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        print("::error::GITHUB_OUTPUT is not set — this must run inside a GitHub Actions step", file=sys.stderr)
        sys.exit(1)

    # actions/checkout expects "owner/repo", not a full URL.
    owner_repo = f"{entry['owner']}/{entry['repo']}"

    with open(output_path, "a", encoding="utf-8") as f:
        f.write(f"repo={owner_repo}\n")
        f.write(f"pinned_version={entry.get('version', '')}\n")

    print(f"Resolved {app_slug} -> {owner_repo} (pinned_version={entry.get('version') or 'latest'})")


if __name__ == "__main__":
    main()