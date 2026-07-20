# Harhub Security Model

## Layers

1. **Row Level Security (Postgres)** — every table has RLS enabled.
   Ownership is resolved through `owns_app(app_id)`, a `security
   definer` function joining `apps → developers → auth.uid()`. No
   table is queryable cross-developer except via explicit `published`
   status checks.
2. **Storage policies** — public buckets scope writes to the owning
   developer via the `{app_id}/...` folder convention. `private-apps`
   has zero client policies (see `docs/storage.md`).
3. **Signed URLs** — the only way to fetch a proprietary binary,
   5-minute TTL, minted per-request by `sign-download`.
4. **SHA256 verification** — computed server-side at scan time,
   stored in `assets.sha256`, and re-verified client-side by both the
   CLI (`download.rs`) and the Android SDK (`HarhubDownloader`) before
   a file is treated as valid. A corrupted or tampered download is
   deleted automatically rather than silently accepted.
5. **GitHub Secrets** — `SUPABASE_SERVICE_KEY` is only ever passed to
   the Action as a `secrets.*` reference, never committed, and only
   used when `visibility: proprietary` is set.
6. **Workflow permissions** — the example workflow requests only
   `contents: write` (needed to push README/metadata commits and
   create Releases) — no broader scopes.

## Ownership verification pattern

`publish-release` deliberately performs its ownership check through a
Postgrest client authenticated with the **caller's own JWT** (so RLS
applies exactly as it would for any other client), and only escalates
to `service_role` after that check passes — for the cross-table writes
RLS alone can't cleanly express (upserting `apps` + `releases` +
`assets` in one atomic-feeling flow). This means the authorization
boundary is enforced by Postgres itself, not by application logic that
could have a bug.

## Threat: repo hijack

Could someone publish an app under a repo they don't own? No —
`apps.repo_owner + repo_name` is unique, and after any upsert,
`publish-release` explicitly re-checks `app.developer_id ===
developer.id`, rejecting with 403 if the row already belongs to a
different developer.

## Threat: shared/leaked download link

Public app links are inherently shareable — that's the point, they're
public. Proprietary app links (`sign-download` URLs) expire in 5
minutes, so a leaked link has a narrow window and can't be re-used
after expiry, unlike a permanent Storage URL would allow.