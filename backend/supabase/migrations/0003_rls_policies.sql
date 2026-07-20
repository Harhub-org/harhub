-- ============================================================
-- Row Level Security — Tables
-- ============================================================

alter table public.users enable row level security;
alter table public.developers enable row level security;
alter table public.categories enable row level security;
alter table public.apps enable row level security;
alter table public.releases enable row level security;
alter table public.assets enable row level security;
alter table public.screenshots enable row level security;
alter table public.download_history enable row level security;

-- ------------------------------------------------------------
-- Helper: current user's role
-- ------------------------------------------------------------

create or replace function public.current_role()
returns user_role
language sql
stable
security definer
set search_path = public
as $$
    select role from public.users where id = auth.uid();
$$;

create or replace function public.is_admin_or_mod()
returns boolean
language sql
stable
security definer
set search_path = public
as $$
    select coalesce(public.current_role() in ('admin', 'moderator'), false);
$$;

create or replace function public.owns_app(target_app_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
    select exists (
        select 1
        from public.apps a
        join public.developers d on d.id = a.developer_id
        where a.id = target_app_id
        and d.user_id = auth.uid()
    );
$$;

-- ------------------------------------------------------------
-- USERS
-- ------------------------------------------------------------

create policy "users can read own profile"
    on public.users for select
    using (id = auth.uid() or public.is_admin_or_mod());

create policy "public profiles are readable"
    on public.users for select
    using (true);

create policy "users can update own profile"
    on public.users for update
    using (id = auth.uid())
    with check (id = auth.uid());

-- ------------------------------------------------------------
-- DEVELOPERS
-- ------------------------------------------------------------

create policy "developer profiles are public"
    on public.developers for select
    using (true);

create policy "user can create own developer profile"
    on public.developers for insert
    with check (user_id = auth.uid());

create policy "developer can update own profile"
    on public.developers for update
    using (user_id = auth.uid() or public.is_admin_or_mod())
    with check (user_id = auth.uid() or public.is_admin_or_mod());

-- ------------------------------------------------------------
-- CATEGORIES (read-only for everyone, managed by admin)
-- ------------------------------------------------------------

create policy "categories are public"
    on public.categories for select
    using (true);

create policy "admin manages categories"
    on public.categories for all
    using (public.is_admin_or_mod())
    with check (public.is_admin_or_mod());

-- ------------------------------------------------------------
-- APPS
-- ------------------------------------------------------------

create policy "published apps are public"
    on public.apps for select
    using (status = 'published' or public.owns_app(id) or public.is_admin_or_mod());

create policy "developer creates own app"
    on public.apps for insert
    with check (
        exists (
            select 1 from public.developers d
            where d.id = developer_id and d.user_id = auth.uid()
        )
    );

create policy "developer updates own app"
    on public.apps for update
    using (public.owns_app(id) or public.is_admin_or_mod())
    with check (public.owns_app(id) or public.is_admin_or_mod());

create policy "developer deletes own app"
    on public.apps for delete
    using (public.owns_app(id) or public.is_admin_or_mod());

-- ------------------------------------------------------------
-- RELEASES
-- ------------------------------------------------------------

create policy "releases follow parent app visibility"
    on public.releases for select
    using (
        exists (
            select 1 from public.apps a
            where a.id = app_id
            and (a.status = 'published' or public.owns_app(a.id) or public.is_admin_or_mod())
        )
    );

create policy "developer manages own releases"
    on public.releases for insert
    with check (public.owns_app(app_id));

create policy "developer updates own releases"
    on public.releases for update
    using (public.owns_app(app_id) or public.is_admin_or_mod())
    with check (public.owns_app(app_id) or public.is_admin_or_mod());

create policy "developer deletes own releases"
    on public.releases for delete
    using (public.owns_app(app_id) or public.is_admin_or_mod());

-- ------------------------------------------------------------
-- ASSETS
-- ------------------------------------------------------------

create policy "assets follow parent release visibility"
    on public.assets for select
    using (
        exists (
            select 1
            from public.releases r
            join public.apps a on a.id = r.app_id
            where r.id = release_id
            and (a.status = 'published' or public.owns_app(a.id) or public.is_admin_or_mod())
        )
    );

create policy "developer manages own assets"
    on public.assets for insert
    with check (
        exists (
            select 1 from public.releases r
            where r.id = release_id and public.owns_app(r.app_id)
        )
    );

create policy "developer updates own assets"
    on public.assets for update
    using (
        exists (select 1 from public.releases r where r.id = release_id and public.owns_app(r.app_id))
        or public.is_admin_or_mod()
    );

create policy "developer deletes own assets"
    on public.assets for delete
    using (
        exists (select 1 from public.releases r where r.id = release_id and public.owns_app(r.app_id))
        or public.is_admin_or_mod()
    );

-- ------------------------------------------------------------
-- SCREENSHOTS
-- ------------------------------------------------------------

create policy "screenshots follow app visibility"
    on public.screenshots for select
    using (
        exists (
            select 1 from public.apps a
            where a.id = app_id
            and (a.status = 'published' or public.owns_app(a.id) or public.is_admin_or_mod())
        )
    );

create policy "developer manages own screenshots"
    on public.screenshots for all
    using (public.owns_app(app_id) or public.is_admin_or_mod())
    with check (public.owns_app(app_id) or public.is_admin_or_mod());

-- ------------------------------------------------------------
-- DOWNLOAD HISTORY (write-only via service role / edge function; users see own)
-- ------------------------------------------------------------

create policy "users see own download history"
    on public.download_history for select
    using (user_id = auth.uid() or public.is_admin_or_mod());

create policy "system inserts download history"
    on public.download_history for insert
    with check (true);

-- ============================================================
-- Row Level Security — Storage Objects
-- ============================================================

-- public-apps, icons, screenshots, banners: public read, owner write
create policy "public bucket read"
    on storage.objects for select
    using (bucket_id in ('public-apps', 'icons', 'screenshots', 'banners'));

create policy "developer uploads to own app folder"
    on storage.objects for insert
    with check (
        bucket_id in ('public-apps', 'icons', 'screenshots', 'banners')
        and exists (
            select 1 from public.apps a
            where a.id::text = (storage.foldername(name))[1]
            and public.owns_app(a.id)
        )
    );

create policy "developer updates own app folder"
    on storage.objects for update
    using (
        bucket_id in ('public-apps', 'icons', 'screenshots', 'banners')
        and exists (
            select 1 from public.apps a
            where a.id::text = (storage.foldername(name))[1]
            and public.owns_app(a.id)
        )
    );

create policy "developer deletes own app folder"
    on storage.objects for delete
    using (
        bucket_id in ('public-apps', 'icons', 'screenshots', 'banners')
        and exists (
            select 1 from public.apps a
            where a.id::text = (storage.foldername(name))[1]
            and public.owns_app(a.id)
        )
    );

-- private-apps: NO public read policy at all — only service_role
-- (used by Edge Functions) can touch this bucket. Owners upload via
-- the Edge Function, never directly, so the client never needs
-- storage.objects access to this bucket.