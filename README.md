# plupdate-db

The community plugin database and submission backend for the
[Plupdate](https://github.com/bootlegcheeseburger/plupdate) macOS app.

## Layout

```
db/        -- vendor JSON files, scrapers, validation scripts, schema
worker/    -- Cloudflare Worker that accepts user submissions
.github/   -- daily scrape cron + validate + Pages publish
```

## Where to start

- **Want to fix or add a plugin?** Read [`db/CONTRIBUTING.md`](db/CONTRIBUTING.md).
  No clone required - edit the JSON directly on GitHub.
- **Want the big picture?** Read [`db/ARCHITECTURE.md`](db/ARCHITECTURE.md).
  One page covering all data-flow paths.
- **Vendor onboarding?** Three tiers in [`db/CONTRIBUTING.md`](db/CONTRIBUTING.md)
  - hand-curated JSON, vendor-hosted JSON (preferred), or HTML scraper.

## Live URLs

- Data: `https://bootlegcheeseburger.github.io/plupdate-db/vendors/index.json`
- Worker submit endpoint: `https://plupdate-submit.<account>.workers.dev/submit`
  (deployed from `worker/`)

## Local dev (rarely needed)

```bash
# data side
cd db
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/validate.py
.venv/bin/python -m scripts.scrape           # run all scrapers
.venv/bin/python -m scripts.scrape --dry-run

# worker side
cd worker
npm install
npx wrangler dev
```

Most contributors never need to touch a terminal - CI handles validation
and the daily scrape runs in Actions.
