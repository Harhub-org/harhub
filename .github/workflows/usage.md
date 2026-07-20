# How to Use Harhub in Your Repo

This guide is for developers who want their GitHub repo to have an
automatic download page powered by Harhub. You don't need deep
GitHub Actions knowledge — just follow the steps below.

## Step 1 — Prepare your repo

Your repo needs at minimum:

- `README.md`
- Your app's binary file(s) (`.apk`, `.exe`, Linux binary, etc.)

Example structure:

```example
my-app/
├── README.md
├── app-arm64.apk
└── app-armeabi.apk
```

## Step 2 — Add the placeholder to README.md

Open `README.md` and place this line wherever you want the download
section to appear (usually right below your title/description):

```markdown
## Download

<!-- HARHUB_DOWNLOAD -->
```

The <!-- HARHUB_DOWNLOAD --> placeholder ***must appear exactly like this** — Harhub searches for this line to know where to insert the
download list. Don't change the text.

## Step 3 — Create the workflow file

Create a .github/workflows/ folder at the root of your repo (if it
doesn't exist yet), then create a new file called harhub.yml inside
it:

```code
my-app/
├── README.md
├── app-arm64.apk
├── app-armeabi.apk
└── .github/
    └── workflows/
        └── harhub.yml
```
