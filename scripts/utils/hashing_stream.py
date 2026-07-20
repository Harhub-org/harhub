"""Streams a remote file just far enough to compute its SHA256 and size,
without ever writing the full binary to disk."""

import hashlib
import requests


def sha256_of_url(url: str, headers: dict | None = None, chunk_size: int = 1024 * 1024) -> tuple[str, int]:
    digest = hashlib.sha256()
    total_size = 0

    with requests.get(url, headers=headers, stream=True, timeout=120) as response:
        response.raise_for_status()
        for chunk in response.iter_content(chunk_size=chunk_size):
            if chunk:
                digest.update(chunk)
                total_size += len(chunk)

    return digest.hexdigest(), total_size