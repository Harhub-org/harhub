create or replace function public.increment_download_count(target_asset_id uuid)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
    update public.assets
    set download_count = download_count + 1
    where id = target_asset_id;

    update public.apps a
    set download_count = a.download_count + 1
    from public.releases r
    where r.id = (select release_id from public.assets where id = target_asset_id)
    and a.id = r.app_id;
end;
$$;

-- Only service_role (edge functions) should call this directly.
revoke execute on function public.increment_download_count(uuid) from public, anon, authenticated;
grant execute on function public.increment_download_count(uuid) to service_role;