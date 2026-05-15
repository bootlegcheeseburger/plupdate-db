"""Template scraper. Copy this file to `scrapers/<your-vendor>.py` and edit.

Leading underscore keeps this file out of `scrapers/registry.py` so the daily
cron doesn't try to run it. After you've adapted it, register your real
scraper in `scrapers/registry.py`.

A scraper's job is to fetch a vendor's public download page (or per-product
pages) and yield one `ScrapedRelease` per plugin found. The runner
(`scripts/scrape.py`) groups releases by vendor and writes the JSON file.

For the simplest real example, see `scrapers/oeksound.py` (~65 lines).
"""
from __future__ import annotations

import re
from typing import Iterable

from .base import ScrapedRelease, fetch, log

# Display name + canonical homepage. These end up in the vendor JSON header.
VENDOR = "Acme Plugins"
HOMEPAGE = "https://example.invalid/acme"

# The page your scraper fetches to find current installer URLs.
DOWNLOADS_URL = "https://example.invalid/acme/downloads"

# Map a product slug (whatever appears in the installer URL or filename)
# to (display name, bundle id, product-page URL). Add real entries here.
KNOWN: dict[str, tuple[str, str, str]] = {
    "superreverb": (
        "SuperReverb",
        "com.acme.SuperReverb",
        "https://example.invalid/acme/products/superreverb",
    ),
    # "minisynth": ("Mini Synth", "com.acme.MiniSynth", "https://..."),
}

# Regex to find installer URLs on the downloads page.
URL_PATTERN = re.compile(
    r"https://example\.invalid/acme/downloads/[^\"'<>\s]+\.pkg",
    re.IGNORECASE,
)

# Regex to extract slug + version from each installer filename.
# Use named groups `slug` and `v`; the runner reads them by name.
FILE_PATTERN = re.compile(
    r"(?P<slug>[A-Za-z][A-Za-z0-9_-]*)-(?P<v>\d+(?:\.\d+){1,3})\.pkg",
)


class SampleScraper:
    name = "_sample"          # filename slug; matches scrapers/_sample.py
    vendor = VENDOR
    homepage = HOMEPAGE
    # Canonical registrable domain for this vendor. Every vendorPage host must
    # equal this or be a subdomain. Every downloadURL host must equal this,
    # be a subdomain, or appear in allowed_download_hosts below.
    trusted_domain = "example.invalid"
    # Extra hostnames allowed for downloads (CDN, object store, etc.).
    # Leave empty if the vendor only serves from trusted_domain or subdomains.
    allowed_download_hosts: list[str] = []
    # Apple Developer Team ID expected to sign this vendor's plugins
    # (10 uppercase alphanumeric chars). Leave as None until confirmed by
    # inspecting an installed bundle's `codesign -dvv` output.
    signing_team_id: str | None = None

    def scrape(self) -> Iterable[ScrapedRelease]:
        html = fetch(DOWNLOADS_URL)
        seen: set[str] = set()
        for url in URL_PATTERN.findall(html):
            m = FILE_PATTERN.search(url)
            if not m:
                continue
            slug = m.group("slug").lower()
            if slug not in KNOWN or slug in seen:
                continue
            seen.add(slug)
            display_name, bundle_id, product_page = KNOWN[slug]
            yield ScrapedRelease(
                bundle_id=bundle_id,
                name=display_name,
                vendor=VENDOR,
                latest_version=m.group("v"),
                download_url=url,
                vendor_page=product_page,
                drm=[{"kind": "ilok"}],
            )
        log.info("%s: %d releases", self.name, len(seen))
