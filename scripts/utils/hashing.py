"""SHA256 hashing helpers for Harhub."""

import hashlib
from pathlib import Path


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Compute the SHA256 hex digest of a file by streaming it in chunks.

    Streaming avoids loading large binaries (APKs, EXEs) fully into memory.
    """
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def file_size_bytes(path: Path) -> int:
    return path.stat().st_size