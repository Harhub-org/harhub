# Harhub Storage

Five buckets (see `backend/supabase/migrations/0002_storage_buckets.sql`):

| Bucket | Public? | Contents |
|---|---|---|
| `public-apps` | Yes | Binaries for public apps that opt out of GitHub Releases |
| `private-apps` | **No** | Binaries for proprietary apps — never directly reachable |
| `icons` | Yes | App icons |
| `screenshots` | Yes | App screenshots |
| `banners` | Yes | App banner/header images |

## Folder convention

All buckets use `{app_id}/{filename}` as the object path. This lets
RLS policies verify ownership via `storage.foldername(name)[1]`
without needing a separate ownership-mapping table — the app UUID
embedded in the path *is* the ownership key.

## Why `private-apps` has no client-facing policy

Every other bucket has `select`/`insert`/`update`/`delete` policies
scoped to the owning developer. `private-apps` intentionally has
**none** — not even a read policy for the owning developer. The only
way in or out is through `service_role`, used exclusively by the
`sign-download` and `publish-release` Edge Functions. This is the
single mechanism that guarantees a proprietary binary can never be
fetched with a permanent, shareable URL: there is no client-reachable
path to the object, full stop.

## Signed URL lifetime

`sign-download` issues Signed URLs with a 300-second TTL. Long enough
to start a download (even a slow one, since the *download* itself
isn't cut off once started — only the *URL's validity window* is),
short enough that a leaked/shared link stops working almost
immediately.