"""Validates asset size and platform before it's allowed into a branch
mirror or GitHub Release — catches oversized/unrecognized files early
with a clear error, instead of letting upload fail midway with a
confusing HTTP error.
"""

# GitHub Release assets: 2 GiB hard limit per file.
MAX_ASSET_SIZE_BYTES = 2 * 1024 * 1024 * 1024

ALLOWED_PLATFORMS = {
    "android", "windows", "linux", "macos", "appimage",
    "deb", "rpm", "zip", "targz", "jar", "plugin", "library",
}


def validate_asset(file_name: str, size_bytes: int, platform: str) -> None:
    if size_bytes <= 0:
        raise ValueError(f"'{file_name}': size_bytes must be positive, got {size_bytes}")

    if size_bytes > MAX_ASSET_SIZE_BYTES:
        size_gb = size_bytes / (1024 ** 3)
        raise ValueError(
            f"'{file_name}' is {size_gb:.2f} GiB, exceeding the 2 GiB GitHub Release "
            f"asset limit. Split the archive or host it elsewhere."
        )

    if platform not in ALLOWED_PLATFORMS:
        raise ValueError(f"'{file_name}': unrecognized platform '{platform}'")


def validate_assets(assets: list[dict]) -> None:
    """Validates a whole batch up front — fails fast before any network
    call (download/upload) is attempted for any asset in the batch.
    """
    errors = []
    for asset in assets:
        try:
            validate_asset(asset["file_name"], asset["size_bytes"], asset["platform"])
        except ValueError as exc:
            errors.append(str(exc))

    if errors:
        raise ValueError("Asset validation failed:\n" + "\n".join(f"  - {e}" for e in errors))