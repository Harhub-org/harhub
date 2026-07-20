# Using Harhub in Your Repo

## 1. Add the placeholder to README.md

```markdown
## Download

<!-- HARHUB_DOWNLOAD -->
```

## 2. Add the workflow

.github/workflows/harhub.yml:
```YAML
name: Harhub Publish

on:
  push:
    tags: ["v*"]

permissions:
  contents: write

jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: hastagaming/harhub/action@v1
        with:
          visibility: public
```

## 3. Tag and push

```git
git tag v1.0.0
git push origin v1.0.0
```

The Action scans the repo for binaries, uploads them as GitHub Release
assets, and commits an updated README.md + metadata.json back to
the repo — all in one run, safe to re-run on the same tag.

## Going proprietary

```YAML
- uses: hastagaming/harhub/action@v1
        with:
          visibility: proprietary
          supabase-url: ${{ secrets.SUPABASE_URL }}
          supabase-service-key: ${{ secrets.SUPABASE_SERVICE_KEY }}
```

Requires a developer profile already linked to your GitHub username
on Harhub (developers.github_username) — the Action will fail with
a clear error if none exists, rather than silently creating an
unclaimed app.