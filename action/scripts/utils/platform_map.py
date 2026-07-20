"""Extension and filename-token based platform/arch detection rules."""

# Order matters: more specific extensions are checked before generic ones.
EXTENSION_PLATFORM_MAP = {
    ".apk": "android",
    ".exe": "windows",
    ".msi": "windows",
    ".appimage": "appimage",
    ".deb": "deb",
    ".rpm": "rpm",
    ".jar": "jar",
    ".zip": "zip",
    ".tar.gz": "targz",
    ".tgz": "targz",
    ".so": "library",
    ".dll": "library",
    ".dylib": "library",
}

# Tokens searched (case-insensitive) inside the filename to disambiguate
# platform when the extension alone is not enough (e.g. a bare Linux binary
# with no extension, or a macOS .zip).
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

# Filenames/dirs that should never be scanned for binaries.
IGNORED_DIR_NAMES = {
    ".git", ".github", "node_modules", "target", "build", "dist",
    ".gradle", ".idea", ".vscode", "__pycache__", ".venv", "venv",
}