# Harhub Database

PostgreSQL schema (see `backend/supabase/migrations/0001_init_schema.sql`).

## Tables

| Table | Purpose |
|---|---|
| `users` | Mirrors `auth.users`, adds `role` (user/developer/moderator/admin) |
| `developers` | Extends a user into a developer identity tied to a GitHub username |
| `categories` | App categories (games, tools, utilities, ...) |
| `apps` | One row per registered app, tied to exactly one GitHub repo |
| `releases` | One row per version of an app; exactly one `is_latest = true` per app (enforced by a partial unique index) |
| `assets` | One row per binary file within a release |
| `screenshots` | App screenshots, ordered by `sort_order` |
| `download_history` | Append-only log of downloads, used for counters and abuse detection |

## Key constraints

- `apps.repo_owner + repo_name` is unique — one app per GitHub repo.
- `assets.release_id + file_name` is unique — no duplicate filenames
  within a release.
- `assets` enforces exactly one of (`public_url`) or
  (`storage_bucket` + `storage_path`) via a check constraint — an asset
  is either a direct link (public) or a Storage pointer (proprietary),
  never both, never neither.
- `sha256` is checked to be exactly 64 hex characters at the DB level,
  not just in application code.

## Enums

`user_role`, `app_visibility`, `app_status`, `asset_platform`,
`asset_arch` — see migration `0001` for the full value lists. Using
Postgres enums (rather than free-text) keeps the platform/status
vocabulary consistent across the Action, CLI, Edge Functions, and
Android SDK, since all four read from the same source of truth.

## increment_download_count

A `security definer` function (migration `0005`) atomically bumps
both `assets.download_count` and the parent `apps.download_count` in
one call, avoiding a read-then-write race under concurrent downloads.
Only `service_role` may execute it — client code never calls it
directly, only `sign-download` does, after issuing a Signed URL.