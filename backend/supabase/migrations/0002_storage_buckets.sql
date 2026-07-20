-- ============================================================
-- Harhub Storage Buckets
-- ============================================================

-- public-apps  : binary untuk aplikasi visibility = 'public' (opsional,
--                 dipakai kalau developer tidak pakai GitHub Release)
-- private-apps : binary untuk aplikasi visibility = 'proprietary'
-- icons        : app icon (public)
-- screenshots  : screenshot app (public)
-- banners      : banner/header image app (public)

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values
    ('public-apps', 'public-apps', true, 524288000, null),        -- 500 MB, public read
    ('private-apps', 'private-apps', false, 524288000, null),     -- 500 MB, no public read
    ('icons', 'icons', true, 5242880, array['image/png','image/jpeg','image/webp','image/x-icon','image/svg+xml']),
    ('screenshots', 'screenshots', true, 10485760, array['image/png','image/jpeg','image/webp']),
    ('banners', 'banners', true, 10485760, array['image/png','image/jpeg','image/webp'])
on conflict (id) do nothing;