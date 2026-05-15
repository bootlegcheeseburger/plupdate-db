"""oeksound — public direct downloads via their CDN."""
from __future__ import annotations

import re
from typing import Iterable

from .base import ScrapedRelease, fetch, log

VENDOR = "oeksound"
DOWNLOADS_URL = "https://oeksound.com/downloads/"

# product slug in URL → (display name, bundle id, product-page URL)
KNOWN = {
    "soothe2": ("soothe2", "com.oeksound.soothe2", "https://oeksound.com/plugins/soothe2"),
    "spiff":   ("spiff",   "com.oeksound.spiff",   "https://oeksound.com/plugins/spiff"),
    "bloom":   ("bloom",   "com.oeksound.bloom",   "https://oeksound.com/plugins/bloom"),
    "soothe":  ("soothe",  "com.oeksound.soothe",  "https://oeksound.com/plugins/soothe-live"),
}

URL_PATTERN = re.compile(
    r'https?://oeksound\.[^"\'<>]+\.(?:pkg|dmg)',
    re.IGNORECASE,
)
FILE_PATTERN = re.compile(
    r"(?P<slug>[a-z][a-z0-9]+)_v(?P<v>\d+(?:\.\d+)*|\d{2,4})_",
    re.IGNORECASE,
)


def _normalize_version(v: str) -> str:
    # "133" → "1.3.3"; "1.1.2" stays.
    if "." in v:
        return v
    if v.isdigit() and 2 <= len(v) <= 4:
        return ".".join(v)
    return v


class OeksoundScraper:
    name = "oeksound"
    vendor = VENDOR
    homepage = "https://oeksound.com/"
    trusted_domain = "oeksound.com"
    # oeksound serves installers from a DigitalOcean Spaces bucket.
    allowed_download_hosts = ["oeksound.ams3.cdn.digitaloceanspaces.com"]

    def scrape(self) -> Iterable[ScrapedRelease]:
        html = fetch(DOWNLOADS_URL)
        seen: set[str] = set()
        for raw in URL_PATTERN.findall(html):
            filename = raw.rsplit("/", 1)[-1]
            m = FILE_PATTERN.match(filename)
            if not m:
                continue
            slug = m.group("slug").lower()
            if slug not in KNOWN or slug in seen:
                continue
            display_name, bundle_id, product_page = KNOWN[slug]
            seen.add(slug)
            yield ScrapedRelease(
                bundle_id=bundle_id,
                name=display_name,
                vendor=VENDOR,
                latest_version=_normalize_version(m.group("v")),
                download_url=raw,
                vendor_page=product_page,
            )
        log.info("oeksound: %d releases", len(seen))
