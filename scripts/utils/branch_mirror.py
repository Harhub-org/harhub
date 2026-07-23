"""Mirrors release assets into a dedicated branch (one branch per tracked
repo) in the Harhub repo itself. Files are placed at the branch root
using their original filename (e.g. app-arm64.apk), always overwritten
with the latest release's content — no per-version subfolders.

Two entry points:
  - mirror_release_to_branch: downloads assets from remote URLs (used by
    publish_from_release.py and sync_tracked_repos.py, which only have
    a GitHub Release asset URL, not a local file).
  - mirror_local_assets_to_branch: copies assets already on local disk
    (used by build_from_source.py, which builds the binary itself).
"""

import shutil
import subprocess
from pathlib import Path

import requests


def _run(*args: str, cwd: Path) -> None:
    subprocess.run(args, cwd=cwd, check=True)


def _branch_exists_remotely(repo_dir: Path, branch: str) -> bool:
    result = subprocess.run(
        ["git", "ls-remote", "--exit-code", "--heads", "origin", branch],
        cwd=repo_dir, capture_output=True, text=True, check=False,
    )
    return result.returncode == 0


def _prepare_worktree(repo_dir: Path, branch: str, worktree_dir: Path) -> None:
    if worktree_dir.exists():
        shutil.rmtree(worktree_dir)

    if _branch_exists_remotely(repo_dir, branch):
        _run("git", "fetch", "origin", branch, cwd=repo_dir)
        _run("git", "worktree", "add", str(worktree_dir), branch, cwd=repo_dir)
    else:
        _run("git", "worktree", "add", "--detach", str(worktree_dir), cwd=repo_dir)
        _run("git", "checkout", "--orphan", branch, cwd=worktree_dir)
        _run("git", "rm", "-rf", "--ignore-unmatch", ".", cwd=worktree_dir)
        readme = worktree_dir / "README.md"
        readme.write_text(
            "# Harhub Downloads\n\n"
            "This branch is managed automatically by Harhub. It stores "
            "binary release files referenced from the main branch's "
            "README — you normally don't need to browse it directly.\n",
            encoding="utf-8",
        )
        _run("git", "add", "README.md", cwd=worktree_dir)
        _run("git", "commit", "-m", "chore(harhub): initialize downloads branch", cwd=worktree_dir)


def _commit_and_push_if_changed(worktree_dir: Path, harhub_repo_dir: Path, branch: str, version: str) -> None:
    _run("git", "add", "-A", cwd=worktree_dir)
    diff = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=worktree_dir, check=False)
    if diff.returncode != 0:
        _run("git", "config", "user.name", "harhub-bot", cwd=worktree_dir)
        _run("git", "config", "user.email", "harhub-bot@users.noreply.github.com", cwd=worktree_dir)
        _run("git", "commit", "-m", f"chore(harhub): sync {branch} to {version}", cwd=worktree_dir)
        _run("git", "push", "origin", branch, cwd=worktree_dir)

    _run("git", "worktree", "remove", "--force", str(worktree_dir), cwd=harhub_repo_dir)


def mirror_release_to_branch(
    harhub_repo_dir: Path,
    branch: str,
    assets: list[dict],
    github_token: str,
    version: str,
) -> dict[str, str]:
    """Downloads each asset (from asset['source_url']) and places it at
    the branch root under its original filename.
    """
    worktree_dir = harhub_repo_dir / f".harhub-worktree-{branch}"
    _prepare_worktree(harhub_repo_dir, branch, worktree_dir)

    headers = {"Authorization": f"Bearer {github_token}"} if github_token else {}
    changed = False
    asset_urls: dict[str, str] = {}

    for existing_file in worktree_dir.iterdir():
        if existing_file.name == ".git":
            continue
        if existing_file.is_file() and existing_file.name not in {a["file_name"] for a in assets}:
            existing_file.unlink()
            changed = True

    for asset in assets:
        file_name = asset["file_name"]
        dest_path = worktree_dir / file_name

        needs_download = True
        if dest_path.exists() and dest_path.stat().st_size == asset["size_bytes"]:
            needs_download = False

        if needs_download:
            with requests.get(asset["source_url"], headers=headers, stream=True, timeout=300) as resp:
                resp.raise_for_status()
                with open(dest_path, "wb") as f:
                    f.writelines(resp.iter_content(chunk_size=1024 * 1024))
            changed = True

        asset_urls[file_name] = f"https://raw.githubusercontent.com/hastagaming/harhub/{branch}/{file_name}"

    version_file = worktree_dir / ".version"
    version_file.write_text(version + "\n", encoding="utf-8")

    if changed:
        _commit_and_push_if_changed(worktree_dir, harhub_repo_dir, branch, version)
    else:
        _run("git", "worktree", "remove", "--force", str(worktree_dir), cwd=harhub_repo_dir)

    return asset_urls


def mirror_local_assets_to_branch(
    harhub_repo_dir: Path,
    branch: str,
    assets: list[dict],
    version: str,
) -> dict[str, str]:
    """Copies each asset from a local file path (asset['local_path']) to
    the branch root under its original filename — used when Harhub builds
    the binary itself from source rather than fetching an already-
    published release asset.
    """
    worktree_dir = harhub_repo_dir / f".harhub-worktree-{branch}"
    _prepare_worktree(harhub_repo_dir, branch, worktree_dir)

    changed = False
    asset_urls: dict[str, str] = {}

    for existing_file in worktree_dir.iterdir():
        if existing_file.name == ".git":
            continue
        if existing_file.is_file() and existing_file.name not in {a["file_name"] for a in assets}:
            existing_file.unlink()
            changed = True

    for asset in assets:
        file_name = asset["file_name"]
        dest_path = worktree_dir / file_name
        source_path = Path(asset["local_path"])

        needs_copy = True
        if dest_path.exists() and dest_path.stat().st_size == asset["size_bytes"]:
            needs_copy = False

        if needs_copy:
            shutil.copyfile(source_path, dest_path)
            changed = True

        asset_urls[file_name] = f"https://raw.githubusercontent.com/hastagaming/harhub/{branch}/{file_name}"

    version_file = worktree_dir / ".version"
    version_file.write_text(version + "\n", encoding="utf-8")

    if changed:
        _commit_and_push_if_changed(worktree_dir, harhub_repo_dir, branch, version)
    else:
        _run("git", "worktree", "remove", "--force", str(worktree_dir), cwd=harhub_repo_dir)

    return asset_urls