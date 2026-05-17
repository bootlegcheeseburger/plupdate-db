"""Template scraper using the strategy library.

Prefer this template over `_sample.py` when the vendor's site has one
of the well-known shapes — JSON-LD product markup, a Sparkle appcast,
a JSON manifest at a known URL, or a sitemap with consistent product
URLs. Each strategy is 10-25 lines of vendor-specific configuration
instead of bespoke HTML parsing.

For boutique vendors with no structured markup, see `_sample.py` (the
regex / fetch pattern). For new vendors authored via Claude, the
scaffold CLI (Step 4) automatically picks between these templates
based on what the prep endpoint detected.

Copy this to `scrapers/<your-vendor>.py` and adapt.
"""
from __future__ import annotations

from typing import Iterable

from .base import ScrapedRelease, log
from .strategies import appcast, jsonld, StrategyMiss


VENDOR = "Acme Plugins"
HOMEPAGE = "https://example.invalid/acme"


class SampleStrategyScraper:
    name = "_sample_strategy"      # leading underscore keeps it out of the registry
    vendor = VENDOR
    homepage = HOMEPAGE
    trusted_domain = "example.invalid"
    allowed_download_hosts: list[str] = []
    signing_team_id: str | None = None

    def scrape(self) -> Iterable[ScrapedRelease]:
        # Strategy 1 — Sparkle appcast for the main product.
        # One ScrapedRelease per call; concat with other strategies'
        # output if the vendor ships multiple plugins.
        try:
            yield from appcast(
                "https://example.invalid/acme/appcast.xml",
                bundle_id="com.acme.SuperReverb",
                name="SuperReverb",
                vendor=VENDOR,
                vendor_page="https://example.invalid/acme/products/superreverb",
            )
        except StrategyMiss as e:
            log.warning("%s: appcast missed: %s", self.name, e)

        # Strategy 2 — JSON-LD on a sibling product page.
        try:
            yield from jsonld(
                "https://example.invalid/acme/products/minisynth",
                bundle_id="com.acme.MiniSynth",
                name="Mini Synth",
                vendor=VENDOR,
            )
        except StrategyMiss as e:
            log.warning("%s: jsonld missed: %s", self.name, e)
