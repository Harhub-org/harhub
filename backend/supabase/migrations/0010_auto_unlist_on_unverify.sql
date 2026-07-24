-- When a developer's verified flag flips to false, automatically demote
-- all of their published apps to draft. Prevents a scenario where a
-- developer is unverified (e.g. for abuse) but their apps stay live.

create or replace function public.unlist_apps_on_unverify()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    if old.verified = true and new.verified = false then
        update public.apps
        set status = 'draft'
        where developer_id = new.id
        and status = 'published';
    end if;
    return new;
end;
$$;

drop trigger if exists trg_unlist_apps_on_unverify on public.developers;

create trigger trg_unlist_apps_on_unverify
    after update of verified on public.developers
    for each row
    execute function public.unlist_apps_on_unverify();