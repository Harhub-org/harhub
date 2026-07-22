"""Harhub on-demand publish job — triggered manually via workflow_dispatch
in the official Harhub repo. Resolves repo/branch/visibility/version from
config/tracked-repos.toml by app_slug, fetches the (pinned or latest)
GitHub Release, and mirrors the assets into a dedicated branch AND the
Harhub repo's own Releases tab.
"""

import os
import sys
from pathlib import Path

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from utils.hashing_stream import sha256_of_url  # noqa: E402
from utils.platform_detect import detect_platform_and_arch  # noqa: E402
from utils.notify import notify_publish  # noqa: E402
from utils.branch_mirror import mirror_release_to_branch  # noqa: E402
from utils.harhub_release import download_then_upload_to_release  # noqa: E402
from utils.tracked_repos import find_tracked_repo  # noqa: E402

GITHUB_API = "https://api.github.com"


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def github_headers(token: str) -> dict:
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def fetch_latest_release(owner: str, repo: str, token: str) -> dict:
    url = f"{GITHUB_API}/repos/{owner}/{repo}/releases/latest"
    resp = requests.get(url, headers=github_headers(token), timeout=30)
    resp.raise_for_status()
    return resp.json()


def fetch_release_by_tag(owner: str, repo: str, tag: str, token: str) -> dict:
    url = f"{GITHUB_API}/repos/{owner}/{repo}/releases/tags/{tag}"
    resp = requests.get(url, headers=github_headers(token), timeout=30)
    resp.raise_for_status()
    return resp.json()


class SupabaseAdmin:
    def __init__(self, url: str, service_key: str):
        self.url = url.rstrip("/")
        self.headers = {
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json",
        }

    def upsert(self, table: str, row: dict, conflict: str) -> dict:
        resp = requests.post(
            f"{self.url}/rest/v1/{table}",
            headers={**self.headers, "Prefer": "resolution=merge-duplicates,return=representation"},
            params={"on_conflict": conflict},
            json=row,
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()
        return result[0] if isinstance(result, list) else result

    def select_one(self, table: str, filters: dict) -> dict | None:
        params = {k: f"eq.{v}" for k, v in filters.items()}
        params["limit"] = "1"
        resp = requests.get(f"{self.url}/rest/v1/{table}", headers=self.headers, params=params, timeout=30)
        resp.raise_for_status()
        rows = resp.json()
        return rows[0] if rows else None


def main() -> None:
    app_slug = env("TARGET_APP_SLUG")

    tracked = find_tracked_repo(app_slug)
    if tracked is None:
        raise RuntimeError(
            f"app_slug '{app_slug}' has no matching entry in config/tracked-repos.toml — add one before running this pipeline."
        )

    target_url = tracked["url"]
    owner, repo = tracked["owner"], tracked["repo"]
    branch = tracked["branch"]
    visibility = tracked["visibility"]
    token = env("GITHUB_TOKEN")

    db = SupabaseAdmin(env("SUPABASE_URL"), env("SUPABASE_SERVICE_KEY"))

    developer = db.select_one("developers", {"github_username": owner})
    if developer is None:
        print(f"[auto] no developer profile for '{owner}' — creating an unverified placeholder")
        developer = db.upsert(
            "developers",
            {"github_username": owner, "verified": False},
            conflict="github_username",
        )

    pinned_version = tracked.get("version", "").strip()
    release = (
        fetch_release_by_tag(owner, repo, pinned_version, token)
        if pinned_version
        else fetch_latest_release(owner, repo, token)
    )
    version = release["tag_name"]
    raw_assets = release.get("assets", [])
    if not raw_assets:
        print(f"{target_url}: release {version} has no binary assets — nothing to publish.")
        return

    prepared_assets = []
    for asset in raw_assets:
        file_name = asset["name"]
        download_url = asset["browser_download_url"]
        print(f"Hashing {file_name}...")
        sha256, size_bytes = sha256_of_url(download_url, headers=github_headers(token))
        platform, arch = detect_platform_and_arch(file_name)
        prepared_assets.append({
            "file_name": file_name,
            "source_url": download_url,
            "platform": platform,
            "arch": arch,
            "size_bytes": size_bytes,
            "sha256": sha256,
        })

    harhub_repo_dir = Path(".").resolve()
    asset_urls = mirror_release_to_branch(
        harhub_repo_dir=harhub_repo_dir,
        branch=branch,
        assets=prepared_assets,
        github_token=token,
        version=version,
    )

    harhub_token = env("HARHUB_REPO_TOKEN")
    if harhub_token:
        download_then_upload_to_release(
            token=harhub_token,
            app_slug=app_slug,
            version=version,
            assets=prepared_assets,
            github_download_headers=github_headers(token),
        )

    app_status = "published" if developer.get("verified") else "draft"
    if app_status == "draft":
        print(f"[warn] {owner}/{repo}: developer not verified — publishing as draft")

    app_row = db.upsert(
        "apps",
        {
            "developer_id": developer["id"],
            "slug": app_slug,
            "name": repo,
            "repo_owner": owner,
            "repo_name": repo,
            "repo_url": target_url,
            "visibility": visibility,
            "status": app_status,
        },
        conflict="repo_owner,repo_name",
    )

    release_row = db.upsert(
        "releases",
        {"app_id": app_row["id"], "version": version, "tag_name": version, "is_latest": True},
        conflict="app_id,version",
    )

    for asset in prepared_assets:
        db.upsert(
            "assets",
            {
                "release_id": release_row["id"],
                "file_name": asset["file_name"],
                "platform": asset["platform"],
                "arch": asset["arch"],
                "size_bytes": asset["size_bytes"],
                "sha256": asset["sha256"],
                "public_url": asset_urls[asset["file_name"]],
            },
            conflict="release_id,file_name",
        )

    notify_publish(
        supabase_url=env("SUPABASE_URL"),
        service_key=env("SUPABASE_SERVICE_KEY"),
        developer_id=developer["id"],
        app_name=repo,
        app_slug=app_slug,
        version=version,
        source="manual",
        asset_urls=asset_urls,
    )

    print(f"Published {target_url} {version} → branch '{branch}' ({len(prepared_assets)} assets).")


if __name__ == "__main__":
    main()