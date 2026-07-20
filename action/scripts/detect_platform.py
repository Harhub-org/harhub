"""Detect platform and architecture for a binary file, based on extension
and filename tokens.
"""

from pathlib import Path

from utils.platform_map import (
    EXTENSION_PLATFORM_MAP,
    FILENAME_PLATFORM_TOKENS,
    ARCH_TOKENS,
)


def _match_extension(filename_lower: str) -> str | None:
    # Check multi-part extensions first (e.g. .tar.gz) before single-part.
    for ext, platform in sorted(EXTENSION_PLATFORM_MAP.items(), key=lambda kv: -len(kv[0])):
        if filename_lower.endswith(ext):
            return platform
    return None


def _match_tokens(filename_lower: str) -> str | None:
    for tokens, platform in FILENAME_PLATFORM_TOKENS:
        if any(token in filename_lower for token in tokens):
            return platform
    return None


def detect_arch(filename_lower: str) -> str:
    for tokens, arch in ARCH_TOKENS:
        if any(token in filename_lower for token in tokens):
            return arch
    return "unknown"


def detect_platform_and_arch(path: Path) -> tuple[str, str]:
    """Returns (platform, arch) as strings matching the asset_platform /
    asset_arch enums in the database schema.
    """
    name_lower = path.name.lower()

    platform = _match_extension(name_lower)

    if platform is None:
        platform = _match_tokens(name_lower)

    if platform is None:
        # No extension and no recognizable token — treat as a raw Linux
        # binary if it's executable, otherwise as a generic library.
        if path.stat().st_mode & 0o111:
            platform = "linux"
        else:
            platform = "library"

    arch = detect_arch(name_lower)

    # Android APKs are always arm64-v8a / armeabi-v7a / x86_64 / universal —
    # default to 'universal' rather than 'unknown' when nothing matched,
    # since most APKs today ship a single universal artifact.
    if platform == "android" and arch == "unknown":
        arch = "universal"

    return platform, arch