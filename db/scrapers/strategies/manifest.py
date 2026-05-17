"""T1 strategy: vendor publishes a JSON manifest at a known URL.

This is the aspirational "vendor publishes the same shape we expect"
case — they own the data, we just fetch it. ~5 lines per vendor.

Expected JSON shape (a subset is fine; missing fields fall to None):

    {
      "plugins": [
        {
          "bundleId": "com.example.foo",
          "name": "Foo",
          "latestVersion": "1.2.3",
          "vendorPage": "https://example.com/foo",
          "drm": [{"kind": "ilok"}]
        }, ...
      ]
    }
"""
from __future__ import annotations

import json
from typing import Iterable, Optional

import requests

from . import StrategyMiss
from scrapers.base import ScrapedRelease, USER_AGENT, DEFAULT_TIMEOUT


def manifest(url: str, *, vendor: str) -> Iterable[ScrapedRelease]:
    """Fetch a JSON plugin manifest and yield one ScrapedRelease per entry.

    Args:
        url: URL of a JSON document with a top-level "plugins" array.
        vendor: vendor display name, used to populate ScrapedRelease.vendor.

    Raises:
        StrategyMiss: response is not JSON, lacks "plugins", or every
            entry is missing bundleId + latestVersion.
    """
    r = requests.get(url, timeout=DEFAULT_TIMEOUT, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    })
    r.raise_for_status()
    try:
        data = r.json()
    except json.JSONDecodeError as e:
        raise StrategyMiss(f"manifest at {url} is not JSON: {e}") from None
    plugins = data.get("plugins")
    if not isinstance(plugins, list):
        raise StrategyMiss(f"manifest at {url} has no 'plugins' array")

    out = []
    for p in plugins:
        if not isinstance(p, dict):
            continue
        bid = p.get("bundleId")
        ver = p.get("latestVersion")
        if not bid or not ver:
            continue
        out.append(ScrapedRelease(
            bundle_id=bid,
            name=p.get("name") or bid,
            vendor=vendor,
            latest_version=str(ver),
            download_url=p.get("downloadURL") or None,
            vendor_page=p.get("vendorPage") or None,
            notes=p.get("notes") or None,
            drm=p.get("drm") or None,
        ))
    if not out:
        raise StrategyMiss(f"manifest at {url} had 'plugins' but no usable entries")
    return out
