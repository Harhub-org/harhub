"""Publishes binaries to a dedicated branch (default: harhub-downloads)
instead of GitHub Releases, and returns raw.githubusercontent.com URLs
that trigger a direct download when clicked — no need to ever visit
the branch itself.

Layout inside the branch:
    {version}/{file_name}

Idempotent: if a file with the same name and identical SHA256 already
exists at that path in the branch, it is not re-committed.
"""

import shutil
import subprocess
from pathlib import Path


def _run(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True)


def _branch_exists_remotely(repo_dir: Path, branch: str) -> bool:
    result = subprocess.run(
        ["git", "ls-remote", "--exit-code", "--heads", "origin", branch],
        cwd=repo_dir, capture_output=True, text=True,
    )
    return result.returncode == 0


def _prepare_worktree(repo_dir: Path, branch: str, worktree_dir: Path) -> None:
    """Sets up worktree_dir checked out to `branch`, creating it as an
    orphan branch (no shared history with main) if it doesn't exist yet.
    """
    if worktree_dir.exists():
        shutil.rmtree(worktree_dir)

    _run("git", "fetch", "origin", branch, cwd=repo_dir) if _branch_exists_remotely(repo_dir, branch) else None

    if _branch_exists_remotely(repo_dir, branch):
        _run("git", "worktree", "add", str(worktree_dir), branch, cwd=repo_dir)
    else:
        # Create a fresh orphan branch in the worktree: no binaries mixed
        # into the main branch's history, and the branch starts clean.
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


def publish_to_branch(
    repo_dir: Path,
    branch: str,
    version: str,
    assets: list[dict],
    scan_root: Path,
    repo_owner: str,
    repo_name: str,
) -> dict[str, str]:
    worktree_dir = repo_dir / ".harhub-worktree"
    _prepare_worktree(repo_dir, branch, worktree_dir)

    version_dir = worktree_dir / version
    version_dir.mkdir(parents=True, exist_ok=True)

    changed = False
    asset_urls: dict[str, str] = {}

    for asset in assets:
        source_path = scan_root / asset["relative_path"]
        dest_path = version_dir / asset["file_name"]

        if dest_path.exists():
            # Already published with identical content — skip re-copy,
            # keeps the branch history free of no-op commits on re-runs.
            existing_size = dest_path.stat().st_size
            if existing_size == asset["size_bytes"]:
                asset_urls[asset["file_name"]] = _raw_url(repo_owner, repo_name, branch, version, asset["file_name"])
                continue

        shutil.copyfile(source_path, dest_path)
        changed = True
        asset_urls[asset["file_name"]] = _raw_url(repo_owner, repo_name, branch, version, asset["file_name"])

    if changed:
        _run("git", "add", "-A", cwd=worktree_dir)
        diff = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=worktree_dir)
        if diff.returncode != 0:
            _run("git", "config", "user.name", "harhub-bot", cwd=worktree_dir)
            _run("git", "config", "user.email", "harhub-bot@users.noreply.github.com", cwd=worktree_dir)
            _run("git", "commit", "-m", f"chore(harhub): publish {version} binaries", cwd=worktree_dir)
            _run("git", "push", "origin", branch, cwd=worktree_dir)

    _run("git", "worktree", "remove", "--force", str(worktree_dir), cwd=repo_dir)

    return asset_urls


def _raw_url(owner: str, name: str, branch: str, version: str, file_name: str) -> str:
    # raw.githubusercontent.com serves binaries with a content type that
    # browsers can't render inline, so clicking the link downloads the
    # file directly — the user never sees the branch or its file tree.
    return f"https://raw.githubusercontent.com/{owner}/{name}/{branch}/{version}/{file_name}"