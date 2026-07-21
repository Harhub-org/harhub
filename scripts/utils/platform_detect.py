"""Standalone platform/arch detection for filenames coming from remote
GitHub Release assets (no local Path/file access needed, unlike the
action/scripts version which also checks file executable bits).

Mirrors the same platform/arch vocabulary used across Harhub:
action/scripts/detect_platform.py, the database enums (asset_platform,
asset_arch), the CLI (cli/src/platform.rs), and the Android SDK.

This file is fully standalone — no import from action/scripts/utils, so
scripts/ never depends on action/.
"""

EXTENSION_PLATFORM_MAP = {
    ".tar.gz": "targz",
    ".apk": "android",
    ".exe": "windows",
    ".msi": "windows",
    ".appimage": "appimage",
    ".deb": "deb",
    ".rpm": "rpm",
    ".jar": "jar",
    ".zip": "zip",
    ".tgz": "targz",
    ".so": "library",
    ".dll": "library",
    ".dylib": "library",
}

FILENAME_PLATFORM_TOKENS = [
    (["darwin", "macos", "osx"], "macos"),
    (["linux"], "linux"),
    (["win32", "win64", "windows"], "windows"),
    (["android"], "android"),
]

ARCH_TOKENS = [
    (["arm64-v8a", "aarch64", "arm64"], "arm64-v8a"),
    (["armeabi-v7a", "armv7", "arm32"], "armeabi-v7a"),
    (["x86_64", "amd64", "win64", "x64"], "x86_64"),
    (["x86", "win32", "i386", "i686"], "x86"),
    (["universal", "fat", "multiarch"], "universal"),
]


def _match_extension(filename_lower: str) -> str | None:
    for ext, platform in sorted(EXTENSION_PLATFORM_MAP.items(), key=lambda kv: -len(kv[0])):
        if filename_lower.endswith(ext):
            return platform
    return None


def _match_tokens(filename_lower: str) -> str | None:
    for tokens, platform in FILENAME_PLATFORM_TOKENS:
        if any(token in filename_lower for token in tokens):
            return platform
    return None


def _detect_arch(filename_lower: str) -> str:
    for tokens, arch in ARCH_TOKENS:
        if any(token in filename_lower for token in tokens):
            return arch
    return "unknown"


def detect_platform_and_arch(file_name: str) -> tuple[str, str]:
    name_lower = file_name.lower()

    platform = _match_extension(name_lower)
    if platform is None:
        platform = _match_tokens(name_lower)
    if platform is None:
        platform = "library"

    arch = _detect_arch(name_lower)

    if platform == "android" and arch == "unknown":
        arch = "universal"

    return platform, arch