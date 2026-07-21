"""Harhub build-from-source job.

For developers who haven't published a compiled binary yet — only source
code in their repo. Detects the project's build system automatically
(Gradle, CMake, Make, Cargo, npm — or an explicit override), runs it, and
mirrors whatever binaries it produces into the target branch.

Build command resolution order:
  1. config/commands.toml entry for this app_slug (always wins if present)
  2. build_command manual input from workflow_dispatch
  3. auto-detected default command for the detected build system
"""

import hashlib
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils.branch_mirror import mirror_local_assets_to_branch
from utils.build_config import load_command_override
from utils.build_systems import (
    detect_build_system,
    run_build,
    find_built_binaries,
    find_binary_by_override,
)
from utils.platform_detect import detect_platform_and_arch


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _parse_repo_url(url: str) -> tuple[str, str]:
    path = urlparse(url).path.strip("/")
    parts = path.removesuffix(".git").split("/")
    if len(parts) < 2:
        raise ValueError(f"Invalid GitHub repo URL: {url}")
    return parts[0], parts[1]


def sha256_and_size(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


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
    target_url = env("TARGET_REPO")
    owner, repo = _parse_repo_url(target_url)

    app_slug = env("TARGET_APP_SLUG")
    branch = env("TARGET_BRANCH").strip() or f"{app_slug}-downloads"
    visibility = env("TARGET_VISIBILITY", "public")
    forced_build_system = env("BUILD_SYSTEM", "auto")
    module_path = env("MODULE_PATH", "")
    build_command_override = env("BUILD_COMMAND_OVERRIDE", "")
    target_repo_dir = Path(env("TARGET_REPO_DIR")).resolve()

    if not target_repo_dir.exists():
        raise RuntimeError(f"TARGET_REPO_DIR '{target_repo_dir}' does not exist — checkout step may have failed.")

    project_dir = target_repo_dir / module_path if module_path else target_repo_dir

    db = SupabaseAdmin(env("SUPABASE_URL"), env("SUPABASE_SERVICE_KEY"))

    developer = db.select_one("developers", {"github_username": owner})
    if developer is None:
        print(f"[auto] no developer profile for '{owner}' — creating an unverified placeholder")
        developer = db.upsert(
            "developers",
            {"github_username": owner, "verified": False},
            conflict="github_username",
        )

    override = load_command_override(app_slug)

    if override:
        print(f"[config] using saved command override for '{app_slug}' from config/commands.toml")
        build_system = detect_build_system(project_dir, override.get("build_system", "auto"))
        run_build(project_dir, build_system, override["build_command"])
        built_binaries = find_binary_by_override(
            project_dir,
            output_path=override.get("output_path", ""),
            output_glob=override.get("output_glob", ""),
        )
    else:
        build_system = detect_build_system(project_dir, forced_build_system)
        print(f"Detected build system: {build_system.name}")
        run_build(project_dir, build_system, build_command_override)
        built_binaries = find_built_binaries(project_dir, build_system)

    version = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=target_repo_dir, capture_output=True, text=True, check=True,
    ).stdout.strip()

    prepared_assets = []
    for binary_path in built_binaries:
        sha256, size_bytes = sha256_and_size(binary_path)
        platform, arch = detect_platform_and_arch(binary_path.name)
        prepared_assets.append({
            "file_name": binary_path.name,
            "local_path": binary_path,
            "platform": platform,
            "arch": arch,
            "size_bytes": size_bytes,
            "sha256": sha256,
        })
        print(f"  built: {binary_path.name} ({platform}/{arch}, {size_bytes} bytes, sha256 {sha256[:12]}...)")

    harhub_repo_dir = Path(env("GITHUB_WORKSPACE", ".")).resolve() / "harhub"
    if not harhub_repo_dir.exists():
        harhub_repo_dir = Path(".").resolve()

    asset_urls = mirror_local_assets_to_branch(
        harhub_repo_dir=harhub_repo_dir,
        branch=branch,
        assets=prepared_assets,
        version=version,
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

    print(f"Built ({build_system.name}) and published {target_url} @ {version} → branch '{branch}' ({len(prepared_assets)} asset(s)).")


if __name__ == "__main__":
    main()