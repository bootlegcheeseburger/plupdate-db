# Plupdate architecture

A one-page map of how data flows in and out of Plupdate.

## Three repos

```
plupdate-db          (public, this repo)
  ├── db/vendors/    -> the data, served via GitHub Pages
  ├── db/scrapers/   -> Python scrapers
  ├── db/scripts/    -> validate, scrape
  ├── worker/        -> Cloudflare Worker (submit + promote)
  └── .github/workflows/{build,validate,scrape}.yml

plupdate             (private now, public on app release)
  └── Sources/, Tests/, Package.swift  -- the macOS app

plupdate-submissions (private, issues-only triage inbox)
  -- no code, just issues created by the Worker
```

## Read path (data out to users)

```
plupdate macOS app
       |
       |  GET https://<owner>.github.io/plupdate-db/vendors/index.json
       |  GET https://<owner>.github.io/plupdate-db/vendors/<slug>.json
       v
GitHub Pages on plupdate-db
       ^
       |  publishes db/vendors/* on push to main (build.yml)
       |
db/vendors/<slug>.json  (source of truth)
```

The app fetches `index.json` first, then each per-vendor file in
parallel. No merged artifact, no build step — Pages serves the raw files
as they appear on `main`.

## Write paths (data in)

Three ways data enters `db/vendors/`. All three converge on a PR against
`main` that CI must validate (schema + index consistency).

### 1. End-user submission (Worker)

```
plupdate macOS app
       |
       |  POST /submit  { submissions: [{ bundleId, name, observedVersion, ... }] }
       v
Cloudflare Worker (plupdate-submit)
       |
       |  rate-limit (KV, hashed IP)
       |  dedupe by bundleId
       v
GitHub Issue on plupdate-submissions     <-- maintainer triage inbox
       |
       |  maintainer hits "Promote" on the admin page
       |
       v
Cloudflare Worker /promote (token-gated)
       |
       |  scaffolds vendors/<slug>.json via GitHub Contents API
       v
PR on plupdate-db                         <-- maintainer reviews + merges
```

Purpose: **discovery of new plugins**, not version corrections. The
submission payload is bare-minimum AAX info — bundleId, name, observed
version. No file paths, no system info, no DRM guesses. DRM is added
later by a maintainer during PR review.

### 2. External-contributor PR

```
contributor (or vendor)
       |
       |  edit vendors/<slug>.json on GitHub (pencil icon -> fork + PR)
       v
PR on plupdate-db
       |
       |  validate.yml: schema check + index consistency
       v
maintainer reviews + merges
```

See `CONTRIBUTING.md` for tier T1/T2/T3 onboarding paths.

### 3. Scrape cron

```
.github/workflows/scrape.yml   (daily)
       |
       |  python scripts/scrape.py
       v
diffs in db/vendors/
       |
       |  classifier: bumps-only vs has-structural
       v
PR on plupdate-db
       |
       |  bumps-only label  -> auto-merge if CI green
       |  has-structural    -> maintainer reviews + merges
       v
db/vendors/ on main
```

A bump = `latestVersion` (and optionally `downloadURL`) changed on an
existing plugin. Anything else — new plugin object, new vendor file,
removed plugin, **any DRM change** — is structural and waits for human
review.

## DRM field

The `drm` field on each plugin is maintainer-curated, never derived from
user submissions or scrapers. Schema kinds: `ilok | authfile | serial |
login | custom`. The app probes the filesystem for `authfile` paths to
color-code an auth dot per row. See `CONTRIBUTING.md` for the field
shape; see `schema.json` for the strict spec.

## What lives where (decision rules)

| Concern | Repo | Reason |
|---|---|---|
| Vendor JSON data | `plupdate-db` | public, PR-able by anyone |
| Scrapers | `plupdate-db` | live next to the data they produce |
| Cloudflare Worker | `plupdate-db` | submissions land here; admin page references the data repo |
| Submission triage inbox | `plupdate-submissions` (private) | issues created by Worker; private to keep user data out of public history |
| macOS app source | `plupdate` (private until release) | separate release cycle, separate issue tracker for app bugs |

## Out of scope

No Railway, no SQLite, no central server, no auth-protected admin
routes on a backend. The only admin surface is the Worker's token-gated
`/admin` page that drives `/promote`. Everything else happens in GitHub's
native UI: issues, PRs, comments.
