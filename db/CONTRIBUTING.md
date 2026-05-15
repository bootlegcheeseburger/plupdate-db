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
