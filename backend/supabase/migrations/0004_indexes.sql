create index idx_apps_developer on public.apps (developer_id);
create index idx_apps_category on public.apps (category_id);
create index idx_apps_status on public.apps (status) where status = 'published';
create index idx_apps_visibility on public.apps (visibility);

create index idx_releases_app on public.releases (app_id);
create index idx_releases_published_at on public.releases (published_at desc);

create index idx_assets_release on public.assets (release_id);
create index idx_assets_platform on public.assets (platform);

create index idx_screenshots_app on public.screenshots (app_id, sort_order);

create index idx_download_history_asset on public.download_history (asset_id);
create index idx_download_history_downloaded_at on public.download_history (downloaded_at desc);

create index idx_developers_user on public.developers (user_id);