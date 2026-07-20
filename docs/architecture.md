# Harhub Architecture

## Overview

Harhub turns an ordinary GitHub repository into a professional app
download page. It is not an app store, not a package registry for
source code, and not a build system — it only manages **binaries,
metadata, README rendering, and the app registry** around them.

## Components

- **GitHub Action** (`action/`) — a composite action developers drop
  into their own repo's workflow. Scans binaries, computes checksums,
  publishes them (GitHub Release for public apps, Supabase Storage for
  proprietary apps), regenerates `metadata.json`, and rewrites the
  `<!-- HARHUB_DOWNLOAD -->` block in `README.md`.
- **Supabase backend** (`backend/`) — Postgres schema, RLS policies,
  storage buckets, and two Edge Functions (`sign-download`,
  `publish-release`) that back the registry.
- **CLI** (`cli/`) — a Rust binary for searching, inspecting,
  installing, and publishing apps from the terminal.
- **Android SDK** (`android-sdk/`) — a Kotlin library (Retrofit +
  Supabase Kotlin SDK) so Android apps can browse and download from
  Harhub natively.

## Data flow — public app

1. Developer pushes a git tag.
2. The Harhub Action scans the repo, finds binaries, computes SHA256.
3. Each binary is uploaded as a GitHub Release asset (idempotent —
   skipped if it already exists on that release).
4. `metadata.json` and `README.md` are regenerated and committed back
   only if their content actually changed.
5. Anyone can download directly from the GitHub Release URL — no
   Harhub backend involvement required for the download itself.

## Data flow — proprietary app

1. Same trigger, same scan step.
2. Binaries are uploaded to the private `private-apps` Storage bucket
   instead of a GitHub Release.
3. `apps` / `releases` / `assets` rows are written via the Supabase
   service role (from CI) or via `publish-release` (from CLI/other
   clients, under the developer's own JWT).
4. Downloads always go through `sign-download`, which issues a
   5-minute Signed URL and logs the download — the binary itself is
   never reachable by a permanent public URL.

## Why this split

Splitting "scan/publish" (Action) from "resolve/serve" (Supabase) lets
public apps work with **zero** Harhub backend dependency at download
time — GitHub's CDN serves the file directly. Proprietary apps opt
into the backend only where it's actually needed: access control.