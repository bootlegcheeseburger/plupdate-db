"""Regex fallback strategy.

Formalizes the existing hand-rolled pattern (fetch a page, regex out
the download URL or version string, map slug -> bundle metadata).
Most boutique AAX vendors will land here for the foreseeable future
because they ship bespoke product pages without structured markup.

The named `regex_extract` function (not `regex`) avoids shadowing
Python's `re` module imports in callers.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional, Pattern

from . import StrategyMiss
from scrapers.base import ScrapedRelease, fetch


def regex_extract(
    url: str,
    *,
    pattern: Pattern,
    version_group: str = "version",
    bundle_id: str,
    name: Optional[str] = None,
    vendor: str,
    vendor_page: Optional[str] = None,
) -> Iterable[ScrapedRelease]:
    """Fetch a page and apply a single regex; emit one ScrapedRelease.

    For vendors with multiple products per scraper, prefer composing
    this in a loop in the per-vendor scraper file rather than trying
    to subsume multi-product logic here.

    Args:
        url: page URL to fetch.
        pattern: compiled regex. Must contain a named group named
            `version_group` (default 'version').
        version_group: name of the capture group with the version
            string. Override to 'v' or similar if needed.
        bundle_id: bundleId this page represents.
        name: display name (defaults to bundle_id).
        vendor: vendor display name.
        vendor_page: optional product page URL (defaults to `url`).

    Raises:
        StrategyMiss: pattern didn't match any text on the page.
    """
    html = fetch(url)
    m = pattern.search(html)
    if not m:
        raise StrategyMiss(f"regex at {url}: pattern matched 0 times")
    try:
        version = m.group(version_group)
    except (IndexError, error_class_for_group()):
        raise StrategyMiss(
            f"regex at {url}: pattern matched but lacks named group {version_group!r}"
        ) from None
    return [ScrapedRelease(
        bundle_id=bundle_id,
        name=name or bundle_id,
        vendor=vendor,
        latest_version=str(version),
        vendor_page=vendor_page or url,
    )]


# Python's `re` module raises `IndexError` for unknown group on
# compiled patterns but `error` for named-group syntax errors. Match
# both defensively.
def error_class_for_group():
    return re.error
