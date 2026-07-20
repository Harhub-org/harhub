"""Recursively scan a repository for binary assets and collect metadata
about each one (platform, arch, size, sha256).
"""

from pathlib import Path

from detect_platform import detect_platform_and_arch
from utils.hashing import sha256_file, file_size_bytes
from utils.platform_map import EXTENSION_PLATFORM_MAP, IGNORED_DIR_NAMES

RECOGNIZED_SUFFIXES = tuple(EXTENSION_PLATFORM_MAP.keys())


def _is_ignored(path: Path, root: Path) -> bool:
    relative_parts = path.relative_to(root).parts
    return any(part in IGNORED_DIR_NAMES for part in relative_parts)


def _looks_like_binary(path: Path) -> bool:
    name_lower = path.name.lower()
    if name_lower.endswith(RECOGNIZED_SUFFIXES):
        return True
    # No known extension: only treat as a candidate binary if it's
    # executable and has no extension at all (typical for Linux/macOS
    # release binaries such as `myapp-linux-x86_64`).
    if path.suffix == "" and path.stat().st_mode & 0o111:
        return True
    return False


def scan_binaries(scan_root: str) -> list[dict]:
    root = Path(scan_root).resolve()
    assets = []

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if _is_ignored(path, root):
            continue
        if not _looks_like_binary(path):
            continue

        platform, arch = detect_platform_and_arch(path)

        assets.append({
            "file_name": path.name,
            "relative_path": str(path.relative_to(root)),
            "platform": platform,
            "arch": arch,
            "size_bytes": file_size_bytes(path),
            "sha256": sha256_file(path),
        })

    # Deterministic ordering: platform, then filename.
    assets.sort(key=lambda a: (a["platform"], a["file_name"]))
    return assets