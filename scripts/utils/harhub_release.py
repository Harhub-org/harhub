"""Publishes assets to a GitHub Release on the Harhub repo itself —
runs alongside the branch mirror so every publish path (manual, build,
sync) ends up both in a branch AND in the Releases tab.

Uses the repo's own GITHUB_TOKEN (Actions' built-in token, write-scoped
to this repo) — NOT HARHUB_READ_TOKEN, which is read-only and scoped to
reading other people's repos.
"""

import tempfile
from pathlib import Path

import requests

GITHUB_API = "https://api.github.com"
HARHUB_REPO = "hastagaming/harhub"


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}


def ensure_harhub_release(token: str, tag_name: str, release_name: str) -> dict:
    """Gets or creates a GitHub Release on the Harhub repo, tagged
    '{app_slug}-{version}' so multiple apps' releases don't collide.
    """
    get_url = f"{GITHUB_API}/repos/{HARHUB_REPO}/releases/tags/{tag_name}"
    resp = requests.get(get_url, headers=_headers(token), timeout=30)
    if resp.status_code == 200:
        return resp.json()

    create_url = f"{GITHUB_API}/repos/{HARHUB_REPO}/releases"
    resp = requests.post(
        create_url,
        headers=_headers(token),
        json={
            "tag_name": tag_name,
            "name": release_name,
            "generate_release_notes": False,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def upload_release_asset(token: str, release: dict, local_path, file_name: str) -> str:
    """Uploads a local file as a release asset. Idempotent — skips if an
    asset with the same name already exists on this release.
    """
    existing = {a["name"]: a for a in release.get("assets", [])}
    if file_name in existing:
        return existing[file_name]["browser_download_url"]

    upload_url = release["upload_url"].split("{")[0]
    headers = {**_headers(token), "Content-Type": "application/octet-stream"}

    with open(local_path, "rb") as f:
        resp = requests.post(upload_url, headers=headers, params={"name": file_name}, data=f, timeout=300)
    resp.raise_for_status()
    return resp.json()["browser_download_url"]


def publish_to_harhub_release(
    token: str,
    app_slug: str,
    version: str,
    assets: list[dict],
) -> dict[str, str]:
    """assets: list of dicts each with 'file_name' and 'local_path' (a
    Path to an already-downloaded/built file) — returns
    {file_name: browser_download_url} from the Harhub repo's own Release.
    """
    tag_name = f"{app_slug}-{version}"
    release = ensure_harhub_release(token, tag_name, f"{app_slug} {version}")

    urls = {}
    for asset in assets:
        url = upload_release_asset(token, release, asset["local_path"], asset["file_name"])
        urls[asset["file_name"]] = url

    return urls


def download_then_upload_to_release(
    token: str,
    app_slug: str,
    version: str,
    assets: list[dict],
    github_download_headers: dict,
) -> dict[str, str]:
    """For assets that only exist as a remote source_url (not yet on
    disk) — downloads each to a temp file, uploads it to the Harhub
    repo's Release, then discards the temp file.
    """
    tag_name = f"{app_slug}-{version}"
    release = ensure_harhub_release(token, tag_name, f"{app_slug} {version}")

    urls = {}
    with tempfile.TemporaryDirectory() as tmp_dir:
        for asset in assets:
            file_name = asset["file_name"]
            local_path = Path(tmp_dir) / file_name

            with requests.get(asset["source_url"], headers=github_download_headers, stream=True, timeout=300) as resp:
                resp.raise_for_status()
                with open(local_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=1024 * 1024):
                        f.write(chunk)

            url = upload_release_asset(token, release, local_path, file_name)
            urls[file_name] = url

    return urls