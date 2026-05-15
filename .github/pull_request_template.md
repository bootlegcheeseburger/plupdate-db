<!--
  Thanks for contributing! Pick one type below and delete the others.
  CI will run validate.py on your changes. Read db/CONTRIBUTING.md if
  you haven't yet.
-->

## Type
<!-- Pick exactly one. Delete the others. -->
- [ ] **New vendor** - adds `db/vendors/<slug>.json` and an entry in `db/vendors/index.json`
- [ ] **Data fix** - corrects fields on an existing `db/vendors/<slug>.json`
- [ ] **Scraper** - adds or fixes a `db/scrapers/*.py`
- [ ] **Schema / tooling** - `db/schema.json`, `db/scripts/**`, or workflows
- [ ] **Worker** - `worker/**`
- [ ] **Docs**

## Vendor slug(s)
<!-- e.g. klevgrand, oeksound. N/A for schema/tooling/worker/docs. -->

## What changed and why
<!-- One or two sentences. Link the source page where the version came from
     if this is a data fix. -->

## Checklist
- [ ] `bundleId` matches the plugin's `Info.plist` exactly (if touched)
- [ ] All `vendorPage` URLs live on `trustedDomain` or a subdomain
- [ ] `db/vendors/index.json` updated alphabetically (for new vendors)
- [ ] I did NOT set `drm` (maintainer-curated)

<!--
  Maintainer notes:
  - `domain-change-reviewed` label bypasses the trustedDomain guard in CI.
  - Path labels are applied automatically by .github/workflows/labeler.yml.
-->
