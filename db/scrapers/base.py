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
    def scrape(self) -> Iterable[ScrapedRelease]: ...


def fetch(url: str) -> str:
    resp = requests.get(
        url,
        timeout=DEFAULT_TIMEOUT,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*"},
    )
    resp.raise_for_status()
    return resp.text


log = logging.getLogger("plupdate.scrapers")
