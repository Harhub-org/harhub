-- Tracks download attempts per (ip_hash, asset_id) in a rolling window,
-- so sign-download can reject abusive request bursts without needing
-- external infra like Redis.

create table public.rate_limit_log (
    id uuid primary key default uuid_generate_v4(),
    ip_hash text not null,
    asset_id uuid not null references public.assets(id) on delete cascade,
    requested_at timestamptz not null default now()
);

create index idx_rate_limit_ip_time on public.rate_limit_log (ip_hash, requested_at desc);

-- Auto-cleanup: drop rows older than 1 hour so this table never grows
-- unbounded. Called opportunistically from sign-download rather than
-- via a separate cron job, to keep infra simple.
create or replace function public.prune_rate_limit_log()
returns void
language sql
security definer
set search_path = public
as $$
    delete from public.rate_limit_log where requested_at < now() - interval '1 hour';
$$;

revoke execute on function public.prune_rate_limit_log() from public, anon, authenticated;
grant execute on function public.prune_rate_limit_log() to service_role;

alter table public.rate_limit_log enable row level security;
-- No client-facing policies at all — service_role (sign-download) only.