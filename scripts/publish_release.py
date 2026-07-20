"""Harhub publish orchestrator.

Flow:
  1. Scan repo for binaries.
  2. Determine the version (input > git tag > short SHA).
  3. If visibility == public:
       - Upload each binary as a GitHub Release asset (creates/reuses the
         release for `version`), collect public download URLs.
     If visibility == proprietary:
       - Upload each binary to Supabase Storage (private-apps), record
         app/release/asset rows via PostgREST.
  4. Generate metadata.json (idempotent merge).
  5. Update README.md's HARHUB_DOWNLOAD block (idempotent replace).
  6. Commit changes back to the repo if anything changed.
"""

import os
import subprocess
import sys
from pathlib import Path

import requests

from scan_binaries import scan_binaries
from generate_metadata import build_metadata, write_metadata
from publish_branch import publish_to_branch
from generate_readme import update_readme
from upload_supabase import SupabaseClient, sync_proprietary_release


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def resolve_version() -> str:
    explicit = env("HARHUB_VERSION").strip()
    if explicit:
        return explicit

    ref_name = env("GITHUB_REF_NAME")
    if ref_name and env("GITHUB_REF", "").startswith("refs/tags/"):
        return ref_name

    sha = env("GITHUB_SHA")
    if sha:
        return sha[:7]

    raise RuntimeError("Could not resolve a version: set the `version` input explicitly.")


def repo_owner_name() -> tuple[str, str]:
    full = env("GITHUB_REPOSITORY")
    if "/" not in full:
        raise RuntimeError("GITHUB_REPOSITORY is not set — this action must run inside GitHub Actions.")
    owner, name = full.split("/", 1)
    return owner, name


def ensure_github_release(token: str, owner: str, name: str, version: str) -> dict:
    api = f"https://api.github.com/repos/{owner}/{name}/releases/tags/{version}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}

    response = requests.get(api, headers=headers, timeout=30)
    if response.status_code == 200:
        return response.json()

    create_api = f"https://api.github.com/repos/{owner}/{name}/releases"
    response = requests.post(
        create_api,
        headers=headers,
        json={"tag_name": version, "name": version, "generate_release_notes": True},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def upload_release_asset(token: str, release: dict, local_path: Path, file_name: str) -> str:
    upload_url_template = release["upload_url"]
    upload_url = upload_url_template.split("{")[0]

    # Skip if the asset already exists on this release (idempotent re-run).
    existing = {a["name"]: a for a in release.get("assets", [])}
    if file_name in existing:
        return existing[file_name]["browser_download_url"]

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/octet-stream",
    }
    with open(local_path, "rb") as f:
        response = requests.post(
            upload_url,
            headers=headers,
            params={"name": file_name},
            data=f,
            timeout=300,
        )
    response.raise_for_status()
    return response.json()["browser_download_url"]


def publish_public(token: str, owner: str, name: str, version: str, assets: list[dict], scan_root: Path) -> dict[str, str]:
    storage_mode = env("HARHUB_STORAGE_MODE", "releases")

    if storage_mode == "branch":
        branch = env("HARHUB_BRANCH_NAME", "harhub-downloads")
        return publish_to_branch(
            repo_dir=scan_root,
            branch=branch,
            version=version,
            assets=assets,
            scan_root=scan_root,
            repo_owner=owner,
            repo_name=name,
        )

    if storage_mode == "releases":
        release = ensure_github_release(token, owner, name, version)
        asset_urls = {}
        for asset in assets:
            local_path = scan_root / asset["relative_path"]
            url = upload_release_asset(token, release, local_path, asset["file_name"])
            asset_urls[asset["file_name"]] = url
        return asset_urls

    raise ValueError(f"Unknown storage-mode '{storage_mode}' — must be 'releases' or 'branch'.")


def publish_proprietary(owner: str, name: str, version: str, assets: list[dict], scan_root: Path) -> dict[str, str]:
    client = SupabaseClient(env("SUPABASE_URL"), env("SUPABASE_SERVICE_KEY"))
    app_slug = name.lower()
    storage_paths = sync_proprietary_release(client, owner, name, app_slug, version, assets, scan_root)

    # For README/metadata we point to the Harhub download endpoint, which
    # issues a Signed URL on demand rather than a static link.
    return {
        file_name: f"{env('SUPABASE_URL')}/functions/v1/sign-download?app={app_slug}&file={file_name}"
        for file_name in storage_paths
    }


def commit_if_changed(paths: list[Path], version: str) -> None:
    if env("HARHUB_COMMIT_CHANGES", "true").lower() != "true":
        return

    changed_paths = [str(p) for p in paths if p.exists()]
    if not changed_paths:
        return

    subprocess.run(["git", "config", "user.name", "harhub-bot"], check=True)
    subprocess.run(["git", "config", "user.email", "harhub-bot@users.noreply.github.com"], check=True)
    subprocess.run(["git", "add", *changed_paths], check=True)

    diff = subprocess.run(["git", "diff", "--cached", "--quiet"])
    if diff.returncode == 0:
        return  # nothing staged, nothing to commit

    subprocess.run(["git", "commit", "-m", f"chore(harhub): update metadata for {version}"], check=True)
    subprocess.run(["git", "push"], check=True)


def set_output(name: str, value: str) -> None:
    output_file = env("GITHUB_OUTPUT")
    if output_file:
        with open(output_file, "a", encoding="utf-8") as f:
            f.write(f"{name}={value}\n")


def main() -> None:
    scan_root = Path(env("HARHUB_SCAN_ROOT", ".")).resolve()
    readme_path = Path(env("HARHUB_README_PATH", "README.md")).resolve()
    metadata_path = Path(env("HARHUB_METADATA_PATH", "metadata.json")).resolve()
    visibility = env("HARHUB_VISIBILITY", "public")
    token = env("GITHUB_TOKEN")

    owner, name = repo_owner_name()
    version = resolve_version()

    assets = scan_binaries(str(scan_root))
    if not assets:
        print("Harhub: no binaries found — nothing to publish.")
        set_output("version", version)
        set_output("asset_count", "0")
        return

    if visibility == "proprietary":
        asset_urls = publish_proprietary(owner, name, version, assets, scan_root)
    elif visibility == "public":
        asset_urls = publish_public(token, owner, name, version, assets, scan_root)
    else:
        raise ValueError(f"Unknown visibility '{visibility}' — must be 'public' or 'proprietary'.")

    metadata = build_metadata(metadata_path, owner, name, version, assets, asset_urls)
    metadata_changed = write_metadata(metadata_path, metadata)
    readme_changed = update_readme(readme_path, assets, asset_urls)

    changed_paths = []
    if metadata_changed:
        changed_paths.append(metadata_path)
    if readme_changed:
        changed_paths.append(readme_path)

    commit_if_changed(changed_paths, version)

    print(f"Harhub: published {len(assets)} asset(s) for version {version}.")
    set_output("version", version)
    set_output("asset_count", str(len(assets)))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"::error::Harhub failed: {exc}", file=sys.stderr)
        sys.exit(1)