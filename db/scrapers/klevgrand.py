"""Klevgrand — direct downloads on each per-product page."""
from __future__ import annotations

import re
from typing import Iterable

from .base import ScrapedRelease, fetch, log

VENDOR = "Klevgrand"
BASE = "https://klevgrand.com"

# product slug → (display name, bundle id)
PRODUCTS = {
    "brusfri": ("Brusfri", "com.klevgrand.Brusfri"),
    "luxe":    ("LUXE",    "com.klevgrand.LUXE"),
    # Add more once bundle ids are confirmed via user submissions:
    # "haaze":     ("Haaze 2",     "com.klevgrand.Haaze2"),
    # "kleverb":   ("Kleverb",     "com.klevgrand.Kleverb"),
    # "dawcassette": ("DAW Cassette", "com.klevgrand.DAWCassette"),
}

URL_PATTERN = re.compile(
    r'https?://klevdata\.klevgrand\.com/plugins/(?P<slug>[a-z][a-z0-9]+)/(?P=slug)_(?P<v>\d+(?:_\d+){1,3})_macOS\.(?:dmg|pkg)',
    re.IGNORECASE,
)


class KlevgrandScraper:
    name = "klevgrand"
    vendor = VENDOR
    homepage = "https://klevgrand.com/"
    trusted_domain = "klevgrand.com"
    allowed_download_hosts: list[str] = []

    def scrape(self) -> Iterable[ScrapedRelease]:
        seen: set[str] = set()
        for slug, (display_name, bundle_id) in PRODUCTS.items():
            page = f"{BASE}/products/{slug}"
            try:
                html = fetch(page)
            except Exception as e:
                log.warning("klevgrand %s: %s", slug, e)
                continue
            m = URL_PATTERN.search(html)
            if not m:
                continue
            version = m.group("v").replace("_", ".")
            yield ScrapedRelease(
                bundle_id=bundle_id,
                name=display_name,
                vendor=VENDOR,
                latest_version=version,
                download_url=m.group(0),
                vendor_page=page,
            )
            seen.add(slug)
        log.info("klevgrand: %d releases", len(seen))
