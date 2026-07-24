"""Harhub central sync job.

For each entry in config/tracked-repos.toml:
  1. Fetch the (pinned or latest) GitHub Release for that repo.
  2. Skip if we've already synced this exact tag (tracked in Supabase).
  3. Hash + detect platform for each asset.
  4. Mirror the assets into that repo's dedicated branch AND the Harhub
     repo's own Releases tab.
  5. Upsert app/release/asset rows in Supabase pointing at the mirrored
     raw.githubusercontent.com URLs.
"""

import os
import sys
from pathlib import Path

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from utils.http_retry import github_request # noqa: E402
from utils.asset_validation import validate_assets # noqa: E402
from utils.tracked_repos import load_all_tracked_repos  # noqa: E402
from utils.hashing_stream import sha256_of_url  # noqa: E402
from utils.platform_detect import detect_platform_and_arch  # noqa: E402
from utils.branch_mirror import mirror_release_to_branch  # noqa: E402
from utils.harhub_release import download_then_upload_to_release  # noqa: E402
from utils.notify import notify_publish  # noqa: E402

GITHUB_API = "https://api.github.com"


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def load_tracked_repos() -> list[dict]:
    repos = load_all_tracked_repos()

    single_slug = env("SYNC_SINGLE_APP_SLUG").strip()
    if single_slug:
        repos = [r for r in repos if r["app_slug"] == single_slug]

    return repos


def github_headers(token: str) -> dict:
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def fetch_latest_release(owner: str, repo: str, token: str) -> dict | None:
    url = f"{GITHUB_API}/repos/{owner}/{repo}/releases/latest"
    resp = github_request("GET", url, headers=github_headers(token))
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def fetch_release_by_tag(owner: str, repo: str, tag: str, token: str) -> dict | None:
    url = f"{GITHUB_API}/repos/{owner}/{repo}/releases/tags/{tag}"
    resp = requests.get(url, headers=github_headers(token), timeout=30)
    if resp.status_code == 404:
        return None
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

    def clear_latest_flag(self, app_id: str) -> None:
        resp = requests.patch(
            f"{self.url}/rest/v1/releases",
            headers=self.headers,
            params={"app_id": f"eq.{app_id}", "is_latest": "eq.true"},
            json={"is_latest": False},
            timeout=30,
        )
        resp.raise_for_status()


def sync_one_repo(entry: dict, token: str, db: SupabaseAdmin, harhub_repo_dir: Path, harhub_token: str) -> None:
    owner = entry["owner"]
    repo = entry["repo"]
    slug = entry["app_slug"]
    branch = entry["branch"]
    visibility = entry["visibility"]
    pinned_version = entry.get("version", "").strip()

    release = (
        fetch_release_by_tag(owner, repo, pinned_version, token)
        if pinned_version
        else fetch_latest_release(owner, repo, token)
    )
    if release is None:
        print(f"[skip] {owner}/{repo}: no releases found")
        return

    version = release["tag_name"]
    raw_assets = release.get("assets", [])
    if not raw_assets:
        print(f"[skip] {owner}/{repo}: release {version} has no binary assets")
        return

    developer = db.select_one("developers", {"github_username": owner})
    if developer is None:
        print(f"[auto] no developer profile for '{owner}' — creating an unverified placeholder")
        developer = db.upsert(
            "developers",
            {"github_username": owner, "verified": False},
            conflict="github_username",
        )

    app_status = "published" if developer.get("verified") else "draft"
    if app_status == "draft":
        print(f"[warn] {owner}/{repo}: developer not verified — publishing as draft")

    app_row = db.upsert(
        "apps",
        {
            "developer_id": developer["id"],
            "slug": slug,
            "name": repo,
            "repo_owner": owner,
            "repo_name": repo,
            "repo_url": f"https://github.com/{owner}/{repo}",
            "visibility": visibility,
            "status": app_status,
        },
        conflict="repo_owner,repo_name",
    )

    existing_release = db.select_one("releases", {"app_id": app_row["id"], "version": version})
    if existing_release is not None:
        print(f"[skip] {owner}/{repo}: {version} already synced")
        return

    prepared_assets = []
    for asset in raw_assets:
        file_name = asset["name"]
        download_url = asset["browser_download_url"]
        print(f"  hashing {file_name}...")
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

    validate_assets(prepared_assets)

    asset_urls = mirror_release_to_branch(
        harhub_repo_dir=harhub_repo_dir,
        branch=branch,
        assets=prepared_assets,
        github_token=token,
        version=version,
    )

    if harhub_token:
        download_then_upload_to_release(
            token=harhub_token,
            app_slug=slug,
            version=version,
            visibility=visibility,
            assets=prepared_assets,
            github_download_headers=github_headers(token),
            release_display_name=f"{repo} — {version}",
        )

    db.clear_latest_flag(app_row["id"])

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
        app_slug=slug,
        app_name=repo,
        version=version,
        source="sync",
        visibility=visibility,
        asset_urls=asset_urls,
    )

    print(f"[ok] {owner}/{repo}: synced {version} into branch '{branch}' ({len(prepared_assets)} assets)")


def main() -> None:
    token = env("GITHUB_TOKEN")
    harhub_token = env("HARHUB_REPO_TOKEN")
    db = SupabaseAdmin(env("SUPABASE_URL"), env("SUPABASE_SERVICE_KEY"))
    repos = load_tracked_repos()
    harhub_repo_dir = Path(".").resolve()

    if not repos:
        print("No tracked repos matched — nothing to sync.")
        return

    for entry in repos:
        try:
            sync_one_repo(entry, token, db, harhub_repo_dir, harhub_token)
        except Exception as exc:
            print(f"[error] {entry['owner']}/{entry['repo']}: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()