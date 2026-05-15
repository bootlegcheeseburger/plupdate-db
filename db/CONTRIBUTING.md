# Contributing

Thanks for helping keep the AAX plugin database accurate. **You don't need to
clone this repo.** Edits happen as PRs against single JSON files; CI checks
your changes automatically.

## Quick paths

- **Fix or update one plugin** → edit `vendors/<vendor>.json` directly on
  GitHub: open the file, hit the pencil icon, make your change, "Propose
  changes." That opens a PR. CI tells you if anything's wrong.
- **Add a brand-new vendor** → start from [`vendors/_sample.json`](vendors/_sample.json) — it
  has every field filled in. Copy its contents into a new
  `vendors/<your-slug>.json` (GitHub's "Add file → Create new file" button),
  edit, and add `"<your-slug>"` to the array in `vendors/index.json`
  (alphabetically). One PR, two files.
- **Add a scraper** so daily auto-refresh keeps your file current — copy
  [`scrapers/_sample.py`](scrapers/_sample.py) and see the bottom section.

## Vendor onboarding tiers (for vendors reading this)

If you make plugins and you'd like Plupdate to know about them, there are
three ways in, ordered by your effort:

- **Tier 1 — hand-curated JSON.** Open a PR with just a new
  `vendors/<your-slug>.json` (copy [`vendors/_sample.json`](vendors/_sample.json)
  as a starting point) and add your slug to `vendors/index.json`. You
  update it whenever you ship. Best for low-frequency releases.
- **Tier 2 (preferred) — vendor-hosted JSON.** Publish the same JSON
  shape (see [`schema.json`](schema.json)) at a stable URL on your own
  site, e.g. `https://yoursite.com/.well-known/plupdate.json`. Our
  "scraper" then becomes a five-line `requests.get(...)`. You own the
  contract; site redesigns can't break us. Open an issue with the URL
  and we'll wire it in. This is the path we recommend if you intend to
  ship updates beyond once a year.
- **Tier 3 — HTML scraper.** A maintainer (or you, or any contributor)
  writes a Python scraper under `scrapers/<slug>.py` that parses your
  download page. Daily cron keeps versions current. Brittle to site
  changes, but works when the vendor isn't engaged. This is the realistic
  default for most vendors.

## Vendor file format

Every `vendors/<slug>.json` follows `schema.json`:

```json
{
  "vendor": "Sound Radix",
  "homepage": "https://www.soundradix.com/",
  "plugins": [
    {
      "bundleId": "com.soundradix.AutoAlignPost",
      "name": "Auto-Align Post",
      "latestVersion": "2.3.3",
      "vendorPage": "https://www.soundradix.com/products/auto-align-post/",
      "downloadURL": null,
      "notes": null
    }
  ]
}
```

Field notes:

- **`bundleId`** must match `CFBundleIdentifier` in the plugin's `Info.plist`
  exactly (case-sensitive). Wrong bundle IDs are the #1 source of "my plugin
  shows as Unrecognized" reports. The Plupdate app surfaces installed bundle
  IDs in the Info popover (Copy ID button).
- **`vendorPage`** should link to the *product page that offers the download*,
  not a generic catalog page. The app sends users here when they click the
  download icon.
- **`downloadURL`** is optional (use `null` if absent). Set it only for vendors
  who serve installers directly — no login wall, no marketing redirect.
- **`latestVersion`** is the version string as the vendor advertises it. No
  `v` prefix.
- **slug** (the `<slug>` in the filename) must be lowercase, ASCII, and unique.
  By convention it's the vendor's recognizable short name (e.g. `klevgrand`).
- **`drm`** is optional. When present, it's an array of method objects. Each
  has a `kind` (`ilok`, `authfile`, `serial`, `login`, or `custom`) plus
  optional `paths` (where the authfile lives on disk) and `notes` (a short
  hint shown to users). Multiple entries mean the plugin accepts any of
  them (e.g. iLok *or* serial). Leave the field out if you aren't sure —
  maintainers fill it in once confirmed.

## What CI checks on your PR

- The vendor file matches `schema.json`.
- `bundleId`s are unique within the file and across all vendor files.
- `vendors/index.json` lists exactly the vendor files that exist on disk,
  sorted alphabetically. (If you forget to add your new slug to the index,
  CI will tell you which line to add.)

If any check fails, the PR shows a red X with a clear message. Fix and push
again — no need to know any local commands.

## Adding a scraper

Optional, but nice: if your vendor has a **public** download page, a Python
scraper under `scrapers/<slug>.py` can keep your `vendors/<slug>.json` current
automatically. The daily cron runs them all and opens a PR with diffs.

Start from [`scrapers/_sample.py`](scrapers/_sample.py): copy it to
`scrapers/<your-slug>.py`, drop the leading underscore, edit the constants
and regexes for your vendor, then register your class in
`scrapers/registry.py` (one import line + one entry in `all_scrapers()`).
For a real-world example with the same shape, see `scrapers/oeksound.py`.

If your vendor's site requires login, skip the scraper and just submit
static `vendors/<slug>.json` updates as needed.

## How user submissions become DB entries

When someone runs the Plupdate macOS app and hits "Contribute N", their
unrecognized-plugin info (bundleId, name, observed version, and any
vendor metadata they manually filled in — *no* file paths, system info,
or plugin contents) is POSTed to a Cloudflare Worker. The Worker:

1. Rate-limits per hashed-IP (never stores raw IP).
2. Dedupes by `bundleId` — repeat submissions for the same plugin get a
   `+1` comment on an open issue rather than a fresh one.
3. Files / appends to an issue in our private `plupdate-submissions`
   triage repo. Only maintainers see those issues.

Maintainers review the inbox, decide which submissions are real new
plugins (not personal forks, not duplicates), and promote them into a PR
against this repo via the Worker's `/promote` route. The promoted PR
scaffolds a vendor entry with the submitted fields — `drm` is always
left blank for the maintainer to fill in during review.

If you're a vendor whose plugin shows up in user submissions, you may
get a friendly nudge to onboard via Tier 2 above.

## What we don't accept

- Personal forks of vendor data — one entry per real plugin.
- Speculative `bundleId`s that haven't been confirmed by inspection.
- Affiliate or tracking URLs.
