-- Enforce that only verified developers can have their apps marked
-- published — unverified developers can still create draft apps, but
-- publish-release / sync jobs must check this before setting
-- status = 'published'.

create or replace function public.is_verified_developer(target_developer_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
    select coalesce(
        (select verified from public.developers where id = target_developer_id),
        false
    );
$$;

alter table public.apps
    add constraint apps_published_requires_verified
    check (
        status != 'published'
        or (select verified from public.developers where id = developer_id) = true
    ) not valid;

-- 'not valid' so existing rows aren't retroactively broken; validate
-- separately once historical data is clean:
-- alter table public.apps validate constraint apps_published_requires_verified;