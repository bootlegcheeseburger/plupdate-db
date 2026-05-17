"""Sitemap walker strategy.

Pulls a vendor's sitemap.xml, filters URLs to a product-page pattern,
fetches each one and runs the caller's per-page extractor. Useful when
a vendor has many products under a consistent URL pattern but no
single combined downloads page.
"""
from __future__ import annotations

import re
from typing import Callable, Iterable, Optional
from xml.etree import ElementTree as ET

from . import StrategyMiss
from scrapers.base import ScrapedRelease, fetch


SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


def sitemap(
    sitemap_url: str,
    *,
    url_filter: re.Pattern,
    extractor: Callable[[str, str], Optional[ScrapedRelease]],
    limit: int = 200,
) -> Iterable[ScrapedRelease]:
    """Fetch sitemap.xml, walk each <loc>, filter by `url_filter`, and
    call `extractor(url, html)` on each match.

    Args:
        sitemap_url: URL of sitemap.xml.
        url_filter: compiled regex to match product-page URLs.
        extractor: callable receiving (page_url, page_html). Return a
            ScrapedRelease or None; None is silently skipped.
        limit: max product pages to fetch per call.

    Raises:
        StrategyMiss: sitemap parses but yields zero matching URLs, or
            every matched page's extractor returned None.
    """
    xml = fetch(sitemap_url)
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as e:
        raise StrategyMiss(f"sitemap at {sitemap_url} is not valid XML: {e}") from None

    locs = []
    for loc in root.findall(f".//{SITEMAP_NS}loc"):
        text = (loc.text or "").strip()
        if text and url_filter.search(text):
            locs.append(text)
        if len(locs) >= limit:
            break
    if not locs:
        raise StrategyMiss(f"sitemap at {sitemap_url}: no URLs matched filter")

    out = []
    for url in locs:
        try:
            html = fetch(url)
        except Exception:
            continue
        rel = extractor(url, html)
        if rel is not None:
            out.append(rel)
    if not out:
        raise StrategyMiss(
            f"sitemap at {sitemap_url}: {len(locs)} candidate page(s) but "
            "extractor returned None for all",
        )
    return out
