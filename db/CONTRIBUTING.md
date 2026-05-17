# Contributing

You don't need to clone. Edits happen as PRs against single JSON files;
CI checks your changes automatically.

## Fix or update a plugin

Open `vendors/<vendor>.json` on GitHub, hit the pencil icon, edit,
"Propose changes." That opens a PR.

## Add a new vendor

Copy [`vendors/_sample.json`](vendors/_sample.json) to
`vendors/<your-slug>.json` (GitHub's "Add file" -> "Create new file"),
edit the fields, and add `"<your-slug>"` to `vendors/index.json`
alphabetically. One PR, two files.

## Field notes

Full spec in [`schema.json`](schema.json). The points that trip people up:

- **`bundleId`** must match `CFBundleIdentifier` in the plugin's
  `Info.plist` exactly. Wrong bundle IDs are the #1 reason a plugin
  shows as Unrecognized. The Plupdate app exposes the installed bundle
  ID in its info popover (Copy ID button). Once an entry is in the DB,
  treat its `bundleId` as immutable - if a vendor genuinely renames the
  bundle, add a new entry rather than mutating the existing one.
- **`trustedDomain`** is the vendor's canonical registrable domain
  (e.g. `klevgrand.com`). Every `vendorPage` URL must live on this
  domain or a subdomain - this is enforced in CI. PRs that try to
  point a vendor's page at an off-domain host will be rejected.
- **`vendorPage`** should link to the product page that offers the
  download, not a generic catalog page. Must be on `trustedDomain` or
  a subdomain. https only. This is the per-plugin "where to get the
  update" pointer.
- **`signingTeamId`** is the vendor's Apple Developer Team ID (10
  uppercase alphanumeric chars, e.g. `Q22ABC3JE7`). Optional, but
  recommended. When present, the app verifies the installed plugin's
  code signature and shows a warning on the row if the installed team
  ID doesn't match. Find a vendor's team ID by running
  `codesign -dvv /Library/Application\ Support/Avid/Audio/Plug-Ins/<plugin>.aaxplugin`
  and copying the `TeamIdentifier=` value. Maintainer-curated; do not
  set without verifying. **Vendor-level only** — if a vendor's catalog
  spans multiple Apple Developer teams (acquisitions, distribution
  umbrellas, legacy migrations), split it into separate vendor files
  rather than mixing teams in one file.
- **`drm`** is maintainer-curated. Leave it out.

## What we don't accept

- Personal forks of vendor data.
- Speculative bundle IDs that haven't been confirmed by inspection.
- Affiliate or tracking URLs.

## Choosing a strategy

New vendor scrapers should prefer a strategy over hand-rolled HTML
parsing. Each strategy is a single function in
`db/scrapers/strategies/`, yielding `ScrapedRelease` objects. Pick the
one that matches the vendor's site shape; fail loudly with
`StrategyMiss` when the expected shape isn't present (the runner
records that outcome in the structured scrape log).

| Strategy | Use when… | Example |
|---|---|---|
| `manifest`  | Vendor publishes a JSON file with the schema's `plugins[]` shape at a stable URL. | T1 aspirational; rare today. |
| `appcast`   | Vendor ships a Sparkle XML appcast feed. | iLok License Manager, some big-vendor desktop apps. |
| `jsonld`    | Product page has `<script type="application/ld+json">` with `SoftwareApplication` / `Product`. | Most modern e-commerce vendor sites. |
| `sitemap`   | Many products under a consistent URL pattern; no single combined downloads page. | Big catalog vendors. |
| `github_releases` | Source lives on GitHub. | Open-source plugins. |
| `regex_extract` | Boutique site, bespoke HTML. The fallback. | Most AAX vendors today. |

For the canonical example, see `scrapers/_sample_strategy.py`. For
existing bespoke scrapers (klevgrand, oeksound, liquidsonics,
soundradix), the regex pattern they implement directly is still the
right call — the strategy library is opt-in for new vendors, not a
forced migration.

The scaffold CLI (`just scaffold-vendor`) picks the best strategy
automatically based on what the prep endpoint detected on the
vendor's homepage.
