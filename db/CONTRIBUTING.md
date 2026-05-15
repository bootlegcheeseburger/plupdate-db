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
  ID in its info popover (Copy ID button).
- **`trustedDomain`** is the vendor's canonical registrable domain
  (e.g. `klevgrand.com`). Every `vendorPage` URL must live on this
  domain or a subdomain - this is enforced in CI. PRs that try to
  point a vendor's page at an off-domain host will be rejected.
- **`vendorPage`** should link to the product page that offers the
  download, not a generic catalog page. Must be on `trustedDomain` or
  a subdomain. https only.
- **`downloadURL`** is optional. Must be on `trustedDomain` (or a
  subdomain), *or* an exact host listed in `allowedDownloadHosts`.
  Only set it when the vendor serves the installer directly - no login
  wall, no marketing redirect. https only.
- **`allowedDownloadHosts`** is an optional list of exact hostnames
  that may serve downloads for legitimate CDN/object-store cases
  (e.g. `vendor.ams3.cdn.digitaloceanspaces.com`). Add a host only
  after manually verifying the vendor actually uses it. Subdomain
  matching does *not* apply - each host is listed verbatim.
- **`drm`** is maintainer-curated. Leave it out.

## What we don't accept

- Personal forks of vendor data.
- Speculative bundle IDs that haven't been confirmed by inspection.
- Affiliate or tracking URLs.
