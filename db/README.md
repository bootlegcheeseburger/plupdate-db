# db/

The crowdsourced data layer for the Plupdate macOS app. Published to
GitHub Pages from `main`. One JSON file per plugin vendor, no build step.

## Where the data lives

```
vendors/
  index.json          # which vendor slugs exist (the app reads this first)
  <vendor>.json       # one file per vendor (Sound Radix, oeksound, etc.)
schema.json           # JSON Schema enforced on every PR
scrapers/             # python scrapers for vendors with public download pages
scripts/scrape.py     # daily auto-refresh (also rebuilds index)
scripts/validate.py   # CI lint of vendor files + index
ARCHITECTURE.md       # one-page paradigm doc
CONTRIBUTING.md       # how to add or fix data, vendor onboarding tiers
```

There is **no build step** and no merged artifact. The app fetches
`vendors/index.json`, then each `vendors/<slug>.json` in parallel, and
merges client-side. The git diff *is* the changelog.

## Contributing

You don't need to clone - see [CONTRIBUTING.md](CONTRIBUTING.md). Two paths:

1. **Edit a vendor file on GitHub** - pencil icon on any
   `vendors/<slug>.json`, propose changes, CI validates.
2. **Use the Plupdate app's Contribute button** - submissions for unknown
   plugins go to a private triage repo via a Cloudflare Worker; a
   maintainer promotes good ones to PRs here. No GitHub account needed.

## Daily refresh

`.github/workflows/scrape.yml` runs every day at 07:17 UTC. For each
vendor that has a scraper, it re-checks the public download page and, if
anything changed, opens a PR. Pure version-bump PRs are auto-merged on
green CI; structural changes wait for human review.

If a vendor's site changes shape and a scraper stops finding releases,
the next run leaves that vendor's file alone (no spurious empty PR) and
the problem surfaces as fewer vendors in the auto-PR than expected.

## Pages URLs

```
https://bootlegcheeseburger.github.io/plupdate-db/vendors/index.json
https://bootlegcheeseburger.github.io/plupdate-db/vendors/<slug>.json
```

The `build-and-publish` workflow stages `db/vendors/*.json` under
`_site/vendors/` on every push to `main`. The Plupdate app's
`Endpoints.swift` (in the separate `plupdate` app repo) points at the
URL above.

## Maintainer notes

If you do clone (rarely needed - most edits happen on GitHub), the
top-level README has local-dev commands. Everything those commands do,
the CI workflows do automatically.
