# Scaffold a new vendor scraper

You are helping the plupdate maintainer onboard a new audio plugin
vendor. Given the candidate URL and the context below, output a
**unified diff** that adds two new files:

1. `db/scrapers/<slug>.py` — a scraper class.
2. `db/vendors/<slug>.json` — the initial vendor JSON.

Plus updates:

3. `db/scrapers/registry.py` — register the new scraper.
4. `db/vendors/index.json` — add the slug, sorted.

## Hard rules

- **Output ONLY a unified diff**, ready for `git apply`. No
  explanations, no prose, no markdown fences around the diff. The
  first line must be `diff --git ...`.
- Prefer a **strategy** over hand-rolled HTML parsing. See the
  strategy table below. Use `regex_extract` only when no strategy
  fits.
- If the candidate is portal-distributed (vendor uses a proprietary
  installer app — e.g., iZotope Product Portal, Waves Central, Flux::
  Center, Kilohearts Installer), set `distribution: "portal"` in the
  vendor JSON with a `portal: { name, url }` object. A scraper file
  is **optional** for portal vendors — include one only if the
  website actually has version info worth scraping for changelogs /
  backup downloads.
- All `vendorPage` URLs MUST be on the vendor's `trustedDomain` (the
  canonical registrable domain).
- `bundleId` values MUST be exact strings observed in shipping
  `.aaxplugin` Info.plists. Guesses based on URL slugs are
  unacceptable — when in doubt, leave the plugins array minimal and
  let users submit observations.
- `signingTeamId`: leave `null` unless you've confirmed by inspecting
  an installed binary.
- The scraper file must pass `python db/scripts/validate.py`.

## Schema reference (vendor JSON)

Required:
- `vendor` (string, display name)
- `trustedDomain` (registrable domain, e.g. `klevgrand.com`)
- `plugins[]` (≥1 entry, each with `bundleId`, `name`, `latestVersion`)

Optional vendor-level:
- `homepage` (URI)
- `signingTeamId` (10 uppercase alphanumeric)
- `distribution` (`scraper` | `portal` | `manual`)
- `portal` (`{ name, url? }` — required when distribution=portal)

Optional plugin-level:
- `vendorPage` (URI on trustedDomain)
- `notes` (string, ≤2000 chars)
- `drm[]` (each `{ kind, paths?, notes? }`, kind ∈
  `ilok|authfile|serial|login|custom`)
- `source` (`{ kind: scraper|manual|appcast|skip, url?, regex? }`)

## Strategies available

| Strategy | Use when… |
|---|---|
| `manifest`        | Vendor publishes the schema's `plugins[]` shape at a stable URL. |
| `appcast`         | Vendor ships a Sparkle XML appcast feed. |
| `jsonld`          | Product page has `<script type="application/ld+json">` with `SoftwareApplication`. |
| `sitemap`         | Many products under a consistent URL pattern. |
| `github_releases` | Source lives on GitHub. |
| `regex_extract`   | Boutique site, bespoke HTML. The fallback. |

Each strategy is a single import from `.strategies`. See
`db/scrapers/_sample_strategy.py` for the canonical shape.

## Two canonical examples

### Strategy-based (preferred for new vendors)

```python
# db/scrapers/exampleco.py
from typing import Iterable
from .base import ScrapedRelease, log
from .strategies import jsonld, StrategyMiss

VENDOR = "Example Co"

class ExampleCoScraper:
    name = "exampleco"
    vendor = VENDOR
    homepage = "https://exampleco.com/"
    trusted_domain = "exampleco.com"
    allowed_download_hosts: list[str] = []
    signing_team_id: str | None = None

    def scrape(self) -> Iterable[ScrapedRelease]:
        try:
            yield from jsonld(
                "https://exampleco.com/products/main-plugin",
                bundle_id="com.exampleco.MainPlugin",
                name="Main Plugin",
                vendor=VENDOR,
            )
        except StrategyMiss as e:
            log.warning("exampleco: jsonld missed: %s", e)
```

### Bespoke regex (when no strategy fits)

```python
# db/scrapers/bespokevendor.py
import re
from typing import Iterable
from .base import ScrapedRelease, fetch, log

VENDOR = "Bespoke Vendor"

URL_PATTERN = re.compile(
    r"https://bespokevendor\.com/downloads/(?P<slug>[a-z]+)-v(?P<v>\d+\.\d+\.\d+)\.pkg",
)

KNOWN = {
    "thunder": ("Thunder", "com.bespokevendor.Thunder"),
}

class BespokeVendorScraper:
    name = "bespokevendor"
    vendor = VENDOR
    homepage = "https://bespokevendor.com/"
    trusted_domain = "bespokevendor.com"
    allowed_download_hosts: list[str] = []
    signing_team_id: str | None = None

    def scrape(self) -> Iterable[ScrapedRelease]:
        html = fetch("https://bespokevendor.com/downloads/")
        seen: set[str] = set()
        for m in URL_PATTERN.finditer(html):
            slug = m.group("slug").lower()
            if slug not in KNOWN or slug in seen:
                continue
            seen.add(slug)
            name, bid = KNOWN[slug]
            yield ScrapedRelease(
                bundle_id=bid,
                name=name,
                vendor=VENDOR,
                latest_version=m.group("v"),
                download_url=m.group(0),
                vendor_page=f"https://bespokevendor.com/products/{slug}",
            )
        log.info("bespokevendor: %d releases", len(seen))
```

## Inputs

```
{INPUT_CONTEXT}
```

## Detected candidates

```
{CANDIDATES_JSON}
```

## Fetched homepage (truncated to ~10KB)

```
{HOMEPAGE_HTML}
```

---

Now output the unified diff. No prose. Start with `diff --git`.
