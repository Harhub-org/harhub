-- ============================================================
-- Harhub Core Schema
-- ============================================================

create extension if not exists "uuid-ossp";
create extension if not exists "pgcrypto";

-- ------------------------------------------------------------
-- ENUM TYPES
-- ------------------------------------------------------------

create type user_role as enum ('user', 'developer', 'moderator', 'admin');
create type app_visibility as enum ('public', 'proprietary');
create type app_status as enum ('draft', 'published', 'archived', 'flagged', 'removed');
create type asset_platform as enum (
    'android', 'windows', 'linux', 'macos',
    'appimage', 'deb', 'rpm', 'zip', 'targz', 'jar', 'plugin', 'library'
);
create type asset_arch as enum (
    'arm64-v8a', 'armeabi-v7a', 'x86', 'x86_64', 'universal', 'unknown'
);

-- ------------------------------------------------------------
-- USERS (mirrors auth.users, extends profile info)
-- ------------------------------------------------------------

create table public.users (
    id uuid primary key references auth.users(id) on delete cascade,
    username text unique not null,
    display_name text,
    avatar_url text,
    role user_role not null default 'user',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),

    constraint username_format check (username ~ '^[a-z0-9_-]{3,32}$')
);

-- ------------------------------------------------------------
-- DEVELOPERS (extends users who own apps)
-- ------------------------------------------------------------

create table public.developers (
    id uuid primary key default uuid_generate_v4(),
    user_id uuid not null references public.users(id) on delete cascade,
    github_username text not null,
    organization_name text,
    verified boolean not null default false,
    bio text,
    website_url text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),

    constraint developers_user_unique unique (user_id),
    constraint github_username_unique unique (github_username)
);

-- ------------------------------------------------------------
-- CATEGORIES
-- ------------------------------------------------------------

create table public.categories (
    id uuid primary key default uuid_generate_v4(),
    slug text unique not null,
    name text not null,
    description text,
    icon text,
    created_at timestamptz not null default now()
);

-- ------------------------------------------------------------
-- APPS
-- ------------------------------------------------------------

create table public.apps (
    id uuid primary key default uuid_generate_v4(),
    developer_id uuid not null references public.developers(id) on delete cascade,
    category_id uuid references public.categories(id) on delete set null,

    slug text unique not null,
    name text not null,
    tagline text,
    description text,

    repo_owner text not null,
    repo_name text not null,
    repo_url text not null,

    visibility app_visibility not null default 'public',
    status app_status not null default 'draft',

    icon_url text,
    banner_url text,

    homepage_url text,
    license text,

    star_count integer not null default 0,
    download_count bigint not null default 0,

    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),

    constraint apps_repo_unique unique (repo_owner, repo_name),
    constraint slug_format check (slug ~ '^[a-z0-9-]{2,64}$')
);

-- ------------------------------------------------------------
-- RELEASES (a version of an app)
-- ------------------------------------------------------------

create table public.releases (
    id uuid primary key default uuid_generate_v4(),
    app_id uuid not null references public.apps(id) on delete cascade,

    version text not null,
    tag_name text,
    changelog text,

    is_prerelease boolean not null default false,
    is_latest boolean not null default false,

    published_at timestamptz not null default now(),
    created_at timestamptz not null default now(),

    constraint releases_app_version_unique unique (app_id, version)
);

-- Ensure only one "latest" release per app
create unique index releases_one_latest_per_app
    on public.releases (app_id)
    where is_latest = true;

-- ------------------------------------------------------------
-- ASSETS (a binary file within a release)
-- ------------------------------------------------------------

create table public.assets (
    id uuid primary key default uuid_generate_v4(),
    release_id uuid not null references public.releases(id) on delete cascade,

    file_name text not null,
    platform asset_platform not null,
    arch asset_arch not null default 'unknown',

    size_bytes bigint not null check (size_bytes > 0),
    sha256 text not null check (char_length(sha256) = 64),

    -- for public repos: direct URL (GitHub Release / branch raw link)
    public_url text,

    -- for proprietary apps: pointer into Supabase Storage
    storage_bucket text,
    storage_path text,

    download_count bigint not null default 0,

    created_at timestamptz not null default now(),

    constraint assets_release_filename_unique unique (release_id, file_name),
    constraint assets_source_check check (
        (public_url is not null and storage_bucket is null and storage_path is null)
        or
        (public_url is null and storage_bucket is not null and storage_path is not null)
    )
);

-- ------------------------------------------------------------
-- SCREENSHOTS
-- ------------------------------------------------------------

create table public.screenshots (
    id uuid primary key default uuid_generate_v4(),
    app_id uuid not null references public.apps(id) on delete cascade,
    image_url text not null,
    caption text,
    sort_order integer not null default 0,
    created_at timestamptz not null default now()
);

-- ------------------------------------------------------------
-- DOWNLOAD HISTORY
-- ------------------------------------------------------------

create table public.download_history (
    id uuid primary key default uuid_generate_v4(),
    asset_id uuid not null references public.assets(id) on delete cascade,
    user_id uuid references public.users(id) on delete set null,

    ip_hash text,
    user_agent text,
    downloaded_at timestamptz not null default now()
);