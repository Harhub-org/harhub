"""Publishes assets to a GitHub Release on the dedicated harhub-releases
repo — keeps the main harhub repo's Releases tab clean.

harhub-releases has three permanent branches:
  - main         — empty/default, never receives releases directly
  - public       — target branch for all visibility=public app releases
  - proprietary  — target branch for all visibility=proprietary app releases

Every release's target_commitish is set to "public" or "proprietary"
based on the app's visibility, so browsing that branch in GitHub always
shows only releases of that kind.
"""

import os
import tempfile
from pathlib import Path

import requests

from utils.hashing_stream import sha256_of_url

GITHUB_API = "https://api.github.com"

HARHUB_RELEASES_REPO = os.environ.get("HARHUB_RELEASES_REPO", "harhub-org/harhub-releases")

BOT_MARKER = "<!-- harhub-bot:managed -->"


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}


def _branch_exists(token: str, branch: str) -> bool:
    url = f"{GITHUB_API}/repos/{HARHUB_RELEASES_REPO}/branches/{branch}"
    resp = github_request(url, headers=_headers(token), timeout=30)
    return resp.status_code == 200


def _get_default_branch_sha(token: str) -> str:
    repo_url = f"{GITHUB_API}/repos/{HARHUB_RELEASES_REPO}"
    resp = github_request(repo_url, headers=_headers(token), timeout=30)
    resp.raise_for_status()
    default_branch = resp.json()["default_branch"]

    ref_url = f"{GITHUB_API}/repos/{HARHUB_RELEASES_REPO}/git/ref/heads/{default_branch}"
    resp = github_request(ref_url, headers=_headers(token), timeout=30)
    resp.raise_for_status()
    return resp.json()["object"]["sha"]


def ensure_visibility_branch(token: str, visibility: str) -> str:
    """Ensures the 'public' or 'proprietary' branch exists in
    harhub-releases, creating it from the default branch if missing.
    Returns the branch name to use as target_commitish.
    """
    branch = "proprietary" if visibility == "proprietary" else "public"

    if _branch_exists(token, branch):
        return branch

    base_sha = _get_default_branch_sha(token)
    create_url = f"{GITHUB_API}/repos/{HARHUB_RELEASES_REPO}/git/refs"
    resp = requests.post(
        create_url,
        headers=_headers(token),
        json={"ref": f"refs/heads/{branch}", "sha": base_sha},
        timeout=30,
    )
    if resp.status_code not in (200, 201, 422):  # 422 = already exists (race)
        resp.raise_for_status()

    return branch


def ensure_harhub_release(token: str, tag_name: str, release_name: str, visibility: str) -> dict:
    target_branch = ensure_visibility_branch(token, visibility)

    get_url = f"{GITHUB_API}/repos/{HARHUB_RELEASES_REPO}/releases/tags/{tag_name}"
    resp = requests.get(get_url, headers=_headers(token), timeout=30)

    if resp.status_code == 200:
        existing = resp.json()
        if BOT_MARKER not in (existing.get("body") or ""):
            raise RuntimeError(
                f"Release tag '{tag_name}' already exists on {HARHUB_RELEASES_REPO} but was "
                f"not created by Harhub's automation (missing bot marker). Refusing to touch it."
            )
        return existing

    create_url = f"{GITHUB_API}/repos/{HARHUB_RELEASES_REPO}/releases"
    resp = requests.post(
        create_url,
        headers=_headers(token),
        json={
            "tag_name": tag_name,
            "target_commitish": target_branch,
            "name": release_name,
            "body": f"{BOT_MARKER}\nAutomatically published and managed by Harhub. Do not edit manually.",
            "generate_release_notes": False,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def upload_release_asset(token: str, release: dict, local_path, file_name: str, expected_sha256: str = "") -> str:
    existing = {a["name"]: a for a in release.get("assets", [])}

    if file_name in existing:
        if expected_sha256:
            remote_hash, _ = sha256_of_url(existing[file_name]["browser_download_url"], headers=_headers(token))
            if remote_hash.lower() != expected_sha256.lower():
                delete_url = f"{GITHUB_API}/repos/{HARHUB_RELEASES_REPO}/releases/assets/{existing[file_name]['id']}"
                requests.delete(delete_url, headers=_headers(token), timeout=30)
            else:
                return existing[file_name]["browser_download_url"]
        else:
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
    visibility: str,
    assets: list[dict],
    release_display_name: str | None = None,
) -> dict[str, str]:
    tag_name = f"{app_slug}-{version}"
    name = release_display_name or f"{app_slug} {version}"
    release = ensure_harhub_release(token, tag_name, name, visibility)

    urls = {}
    for asset in assets:
        url = upload_release_asset(
            token, release, asset["local_path"], asset["file_name"],
            expected_sha256=asset.get("sha256", ""),
        )
        urls[asset["file_name"]] = url

    return urls


def download_then_upload_to_release(
    token: str,
    app_slug: str,
    version: str,
    visibility: str,
    assets: list[dict],
    github_download_headers: dict,
    release_display_name: str | None = None,
) -> dict[str, str]:
    tag_name = f"{app_slug}-{version}"
    name = release_display_name or f"{app_slug} {version}"
    release = ensure_harhub_release(token, tag_name, name, visibility)

    urls = {}
    with tempfile.TemporaryDirectory() as tmp_dir:
        for asset in assets:
            file_name = asset["file_name"]
            local_path = Path(tmp_dir) / file_name

            with requests.get(asset["source_url"], headers=github_download_headers, stream=True, timeout=300) as resp:
                resp.raise_for_status()
                with open(local_path, "wb") as f:
                    f.writelines(resp.iter_content(chunk_size=1024 * 1024))

            url = upload_release_asset(
                token, release, local_path, file_name,
                expected_sha256=asset.get("sha256", ""),
            )
            urls[file_name] = url

    return urls