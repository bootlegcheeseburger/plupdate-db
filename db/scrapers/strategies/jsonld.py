"""JSON-LD extraction strategy.

Many modern e-commerce / product pages ship structured data in
`<script type="application/ld+json">` blocks (schema.org Product or
SoftwareApplication). When a vendor does this, version extraction is
deterministic — no HTML scraping required.

Worth trying first before falling back to regex. Pair with the
`scaffold-prep` endpoint which auto-detects JSON-LD on candidate pages.
"""
from __future__ import annotations

import json
import re
from typing import Iterable, Optional

from . import StrategyMiss
from scrapers.base import ScrapedRelease, fetch


JSONLD_BLOCK = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)


def jsonld(
    url: str,
    *,
    bundle_id: str,
    name: Optional[str] = None,
    vendor: str,
) -> Iterable[ScrapedRelease]:
    """Extract the first SoftwareApplication / Product JSON-LD block
    from a page and yield one ScrapedRelease.

    Args:
        url: product page URL.
        bundle_id: bundleId this page represents.
        name: display name override; falls back to JSON-LD `name`.
        vendor: vendor display name.

    Raises:
        StrategyMiss: no JSON-LD block found, or none with a usable
            softwareVersion / version field.
    """
    html = fetch(url)
    blocks = JSONLD_BLOCK.findall(html)
    if not blocks:
        raise StrategyMiss(f"jsonld at {url}: no <script type=application/ld+json> blocks")

    for raw in blocks:
        try:
            data = json.loads(raw.strip())
        except json.JSONDecodeError:
            continue
        # JSON-LD blocks can be a single object, an array, or wrapped
        # in @graph. Normalize to a list of candidate objects.
        candidates = []
        if isinstance(data, list):
            candidates.extend(data)
        elif isinstance(data, dict):
            graph = data.get("@graph")
            if isinstance(graph, list):
                candidates.extend(graph)
            else:
                candidates.append(data)

        for c in candidates:
            if not isinstance(c, dict):
                continue
            t = c.get("@type")
            types = t if isinstance(t, list) else [t]
            if not any(x in ("SoftwareApplication", "Product") for x in types if isinstance(x, str)):
                continue
            version = c.get("softwareVersion") or c.get("version")
            if not version:
                continue
            return [ScrapedRelease(
                bundle_id=bundle_id,
                name=name or c.get("name") or bundle_id,
                vendor=vendor,
                latest_version=str(version),
                download_url=(c.get("downloadUrl") or None),
                vendor_page=url,
            )]
    raise StrategyMiss(f"jsonld at {url}: no SoftwareApplication/Product with softwareVersion")
