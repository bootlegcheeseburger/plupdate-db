# Architecture

```
plupdate-db           public  - vendor JSON, scrapers, scripts
plupdate              private - macOS app + Cloudflare Worker
plupdate-submissions  private - triage issues from user submissions
```

Three write paths converge on PRs against `main`:

1. **User submission** - the macOS app POSTs to a Cloudflare Worker
   (in the `plupdate` repo) that files an issue in
   `plupdate-submissions`. A maintainer promotes the good ones into
   a PR here via the Worker's `/promote` endpoint.
2. **Direct PR** - anyone with a GitHub account can edit a vendor
   file via the pencil icon.
3. **Daily scrape** - `.github/workflows/scrape.yml` opens a PR with
   detected version bumps; bumps-only PRs auto-merge on green CI.

CI enforces `schema.json` and index consistency. `drm` is
maintainer-curated; never derived from submissions or scrapes.
