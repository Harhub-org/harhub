"""Upload proprietary binaries to Supabase Storage (private-apps bucket)
and record app/release/asset metadata via PostgREST, using the service_role
key. This script is only invoked when visibility == 'proprietary'.
"""

import os
from pathlib import Path

import requests


class SupabaseClient:
    def __init__(self, url: str, service_key: str):
        if not url or not service_key:
            raise ValueError(
                "supabase-url and supabase-service-key inputs are required "
                "when visibility is 'proprietary'."
            )
        self.url = url.rstrip("/")
        self.service_key = service_key
        self.headers = {
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
        }

    def upload_binary(self, local_path: Path, app_id: str, file_name: str) -> str:
        """Uploads to private-apps/{app_id}/{file_name}. Returns storage_path."""
        storage_path = f"{app_id}/{file_name}"
        upload_url = f"{self.url}/storage/v1/object/private-apps/{storage_path}"

        with open(local_path, "rb") as f:
            response = requests.put(
                upload_url,
                headers={
                    **self.headers,
                    "Content-Type": "application/octet-stream",
                    "x-upsert": "true",
                },
                data=f,
                timeout=300,
            )
        response.raise_for_status()
        return storage_path

    def upsert_row(self, table: str, row: dict, conflict_columns: str) -> dict:
        response = requests.post(
            f"{self.url}/rest/v1/{table}",
            headers={
                **self.headers,
                "Content-Type": "application/json",
                "Prefer": f"resolution=merge-duplicates,return=representation",
            },
            params={"on_conflict": conflict_columns},
            json=row,
            timeout=30,
        )
        response.raise_for_status()
        result = response.json()
        return result[0] if isinstance(result, list) else result

    def select_one(self, table: str, filters: dict) -> dict | None:
        params = {f"{k}": f"eq.{v}" for k, v in filters.items()}
        params["limit"] = "1"
        response = requests.get(
            f"{self.url}/rest/v1/{table}",
            headers=self.headers,
            params=params,
            timeout=30,
        )
        response.raise_for_status()
        rows = response.json()
        return rows[0] if rows else None


def sync_proprietary_release(
    client: SupabaseClient,
    repo_owner: str,
    repo_name: str,
    app_slug: str,
    version: str,
    assets: list[dict],
    binaries_root: Path,
) -> dict[str, str]:
    """Ensures developer/app/release/asset rows exist, uploads each binary,
    and returns a dict of {file_name: storage_path} for downstream metadata.
    """
    developer = client.select_one("developers", {"github_username": repo_owner})
    if developer is None:
        raise RuntimeError(
            f"No developer profile found for GitHub user '{repo_owner}'. "
            f"The developer must sign up on Harhub and link their GitHub "
            f"account before the first proprietary publish."
        )

    app_row = client.upsert_row(
        "apps",
        {
            "developer_id": developer["id"],
            "slug": app_slug,
            "name": app_slug,
            "repo_owner": repo_owner,
            "repo_name": repo_name,
            "repo_url": f"https://github.com/{repo_owner}/{repo_name}",
            "visibility": "proprietary",
            "status": "published",
        },
        conflict_columns="repo_owner,repo_name",
    )

    release_row = client.upsert_row(
        "releases",
        {
            "app_id": app_row["id"],
            "version": version,
            "is_latest": True,
        },
        conflict_columns="app_id,version",
    )

    storage_paths: dict[str, str] = {}
    for asset in assets:
        local_path = binaries_root / asset["relative_path"]
        storage_path = client.upload_binary(local_path, app_row["id"], asset["file_name"])
        storage_paths[asset["file_name"]] = storage_path

        client.upsert_row(
            "assets",
            {
                "release_id": release_row["id"],
                "file_name": asset["file_name"],
                "platform": asset["platform"],
                "arch": asset["arch"],
                "size_bytes": asset["size_bytes"],
                "sha256": asset["sha256"],
                "storage_bucket": "private-apps",
                "storage_path": storage_path,
            },
            conflict_columns="release_id,file_name",
        )

    return storage_paths