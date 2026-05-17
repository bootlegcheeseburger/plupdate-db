"""Scraper interface for vendor download pages.

Each scraper resolves the latest version (and ideally a direct macOS installer URL)
for one or more bundle ids. The runner writes one JSON file per vendor under
data/vendors/<scraper.name>.json; build.py aggregates them into dist/plugins.json.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable, Optional, Protocol

import requests

USER_AGENT = "PlupdateScraper/0.1 (+https://github.com/dantimmons/plupdate)"
DEFAULT_TIMEOUT = 30


@dataclass
class ScrapedRelease:
    bundle_id: str
    name: str
    vendor: str
    latest_version: str
    download_url: Optional[str] = None
    vendor_page: Optional[str] = None
    notes: Optional[str] = None
    drm: Optional[list[dict]] = None


class Scraper(Protocol):
    name: str               # slug used as filename: vendors/<name>.json
    vendor: str             # display name for the vendor file's "vendor" field
    homepage: str           # vendor homepage URL
    trusted_domain: str     # canonical registrable domain (e.g. "klevgrand.com")
    # Extra hostnames allowed to serve downloads (CDN, object store, etc.).
    # Default empty; override per scraper when the vendor uses an off-domain host.
    allowed_download_hosts: list[str]
    # Apple Developer Team ID expected to sign this vendor's plugins (10
    # uppercase alphanumeric chars). Optional; leave as None until you've
    # confirmed by inspecting an installed bundle's signature. When set,
    # the app warns end users on mismatch with the installed plugin.
    signing_team_id: Optional[str]
    def scrape(self) -> Iterable[ScrapedRelease]: ...

    # Optional per-plugin override. The runner calls this when a plugin in
    # the existing vendor JSON has `source.kind == "scraper"` with a URL
    # override (e.g. an outlier product page that differs from siblings).
    # Default implementation runs scrape() and filters; override when a
    # vendor has cheap per-product fetching to skip the full crawl.
    def scrape_one(self, bundle_id: str, url: Optional[str] = None) -> Optional[ScrapedRelease]: ...


def default_scrape_one(scraper: "Scraper", bundle_id: str, url: Optional[str] = None) -> Optional[ScrapedRelease]:
    """Default scrape_one helper: filters scrape() by bundle_id, ignores url
    override. Use as the fallback in the runner when a Scraper doesn't
    implement scrape_one().
    """
    for r in scraper.scrape():
        if r.bundle_id == bundle_id:
            return r
    return None


def fetch(url: str) -> str:
    resp = requests.get(
        url,
        timeout=DEFAULT_TIMEOUT,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*"},
    )
    resp.raise_for_status()
    return resp.text


log = logging.getLogger("plupdate.scrapers")
