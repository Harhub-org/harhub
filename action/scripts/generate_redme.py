"""Replace the <!-- HARHUB_DOWNLOAD --> placeholder in README.md with a
clean, collapsible, platform-grouped download section.
"""

import re
from pathlib import Path

PLACEHOLDER = "<!-- HARHUB_DOWNLOAD -->"

PLATFORM_LABELS = {
    "android": "Android",
    "windows": "Windows",
    "linux": "Linux",
    "macos": "macOS",
    "appimage": "AppImage",
    "deb": "Debian / Ubuntu (.deb)",
    "rpm": "Fedora / RHEL (.rpm)",
    "zip": "ZIP Archive",
    "targz": "TAR.GZ Archive",
    "jar": "Java (.jar)",
    "plugin": "Plugin",
    "library": "Library",
}

# Preferred display order; anything not listed falls back to alphabetical.
PLATFORM_ORDER = [
    "android", "windows", "linux", "macos", "appimage",
    "deb", "rpm", "zip", "targz", "jar", "plugin", "library",
]


def _group_by_platform(assets: list[dict], asset_urls: dict[str, str]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for asset in assets:
        grouped.setdefault(asset["platform"], []).append(asset)
    for platform_assets in grouped.values():
        platform_assets.sort(key=lambda a: a["file_name"])
    return grouped


def build_download_block(assets: list[dict], asset_urls: dict[str, str]) -> str:
    grouped = _group_by_platform(assets, asset_urls)

    ordered_platforms = [p for p in PLATFORM_ORDER if p in grouped]
    ordered_platforms += sorted(p for p in grouped if p not in PLATFORM_ORDER)

    lines = ["## Download", "", "<details>", "<summary>Download</summary>", ""]

    for platform in ordered_platforms:
        label = PLATFORM_LABELS.get(platform, platform.title())
        lines.append(f"### {label}")
        lines.append("")
        for asset in grouped[platform]:
            url = asset_urls.get(asset["file_name"], "#")
            lines.append(f"- [{asset['file_name']}]({url})")
        lines.append("")

    lines.append("</details>")

    return "\n".join(lines)


def update_readme(readme_path: Path, assets: list[dict], asset_urls: dict[str, str]) -> bool:
    """Returns True if README content changed."""
    if not readme_path.exists():
        raise FileNotFoundError(
            f"{readme_path} not found — Harhub requires a README.md with a "
            f"{PLACEHOLDER} placeholder."
        )

    original = readme_path.read_text(encoding="utf-8")

    if PLACEHOLDER not in original:
        raise ValueError(
            f"{readme_path} does not contain the {PLACEHOLDER} placeholder. "
            f"Add it where you want the download section to appear."
        )

    download_block = build_download_block(assets, asset_urls)

    # Replace only the first occurrence, keep the placeholder comment itself
    # so subsequent runs remain idempotent and re-locatable.
    updated = re.sub(
        re.escape(PLACEHOLDER),
        f"{PLACEHOLDER}\n\n{download_block}",
        original,
        count=1,
    )

    # Strip any previously-generated block on a re-run: everything between
    # the placeholder and the next top-level heading or EOF gets replaced,
    # not duplicated. We do this by detecting a prior "## Download" block
    # right after the placeholder and collapsing it before inserting fresh.
    updated = _collapse_previous_block(original, updated)

    if updated == original:
        return False

    readme_path.write_text(updated, encoding="utf-8")
    return True


def _collapse_previous_block(original: str, freshly_inserted: str) -> str:
    """If README already had a generated block after the placeholder from a
    previous run, remove the stale one so re-runs don't stack duplicates.
    """
    pattern = re.compile(
        re.escape(PLACEHOLDER) + r"\n\n## Download\n\n<details>\n<summary>Download</summary\n?>.*?</details>",
        re.DOTALL,
    )

    if pattern.search(original):
        # There was already a generated block — replace old block with new
        # block computed from freshly_inserted's own new block content.
        new_block_match = re.search(
            re.escape(PLACEHOLDER) + r"\n\n(## Download.*?</details>)",
            freshly_inserted,
            re.DOTALL,
        )
        if new_block_match:
            new_block = new_block_match.group(1)
            return pattern.sub(
                re.escape(PLACEHOLDER).replace("\\", "") + f"\n\n{new_block}",
                original,
                count=1,
            )

    return freshly_inserted