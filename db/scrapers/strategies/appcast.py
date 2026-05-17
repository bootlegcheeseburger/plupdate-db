"""Sparkle appcast XML strategy.

Sparkle is THE macOS update-feed standard. The format is well-defined:
an RSS-flavored XML document where each <item> is a release with
<sparkle:version>, <sparkle:shortVersionString>, and an <enclosure
url=...> pointing at the installer.

Use for vendors that ship a Sparkle-managed desktop app. Most boutique
AAX vendors don't, but a handful do (iLok License Manager, some
NI/iZotope ancillary tools), plus the per-plugin `source.kind="appcast"`
override case where a maintainer points the runner at a found feed.
"""
from __future__ import annotations

from typing import Iterable, Optional
import re
from xml.etree import ElementTree as ET

from . import StrategyMiss
from scrapers.base import ScrapedRelease, fetch


NS = {
    "sparkle": "http://www.andymatuschak.org/xml-namespaces/sparkle",
}


def appcast(
    url: str,
    *,
    bundle_id: str,
    name: Optional[str] = None,
    vendor: str,
    vendor_page: Optional[str] = None,
) -> Iterable[ScrapedRelease]:
    """Parse a Sparkle appcast and yield the newest version as a single
    ScrapedRelease. (Sparkle feeds are typically one-plugin so we don't
    iterate to multiple releases.)

    Args:
        url: URL of the appcast XML.
        bundle_id: the bundleId this feed represents (Sparkle feeds
            don't carry the bundleId themselves).
        name: display name; if None, falls back to the channel <title>.
        vendor: vendor display name.
        vendor_page: optional product page URL.

    Raises:
        StrategyMiss: feed parses but contains no <item> elements with
            a usable version + enclosure.
    """
    xml = fetch(url)
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as e:
        raise StrategyMiss(f"appcast at {url} is not valid XML: {e}") from None

    channel = root.find("channel")
    if channel is None:
        raise StrategyMiss(f"appcast at {url} has no <channel>")

    items = channel.findall("item")
    if not items:
        raise StrategyMiss(f"appcast at {url} has no <item> elements")

    # Walk items oldest -> newest if possible; Sparkle convention is
    # newest first but feeds vary. Take the entry with the highest
    # sparkle:shortVersionString (numeric collation).
    def short_ver(item):
        e = item.find("sparkle:shortVersionString", NS)
        if e is not None and (e.text or "").strip():
            return e.text.strip()
        # Fallback: sparkle:version (build number) or <title>.
        v = item.find("sparkle:version", NS)
        if v is not None and (v.text or "").strip():
            return v.text.strip()
        return ""

    def ver_key(v: str):
        return tuple(int(p) if p.isdigit() else p for p in re.split(r"[.\-_]", v))

    items_sorted = sorted(items, key=lambda it: ver_key(short_ver(it)), reverse=True)
    newest = items_sorted[0]
    version = short_ver(newest)
    if not version:
        raise StrategyMiss(f"appcast at {url}: newest item has no version")

    enclosure = newest.find("enclosure")
    download_url = enclosure.get("url") if enclosure is not None else None

    if name is None:
        title_el = channel.find("title")
        name = (title_el.text or bundle_id).strip() if title_el is not None else bundle_id

    return [ScrapedRelease(
        bundle_id=bundle_id,
        name=name,
        vendor=vendor,
        latest_version=version,
        download_url=download_url,
        vendor_page=vendor_page,
    )]
