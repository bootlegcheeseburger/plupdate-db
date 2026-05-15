"""LiquidSonics — public direct downloads served via /dl/serve.php."""
from __future__ import annotations

import re
from typing import Iterable

from .base import ScrapedRelease, fetch, log

VENDOR = "LiquidSonics"
DOWNLOADS_URL = "https://www.liquidsonics.com/downloads/"

_BASE = "https://www.liquidsonics.com/software"
# product token in the install path → (display name, bundle id, product page URL)
KNOWN = {
    "cinematic_rooms_professional": ("Cinematic Rooms Professional", "com.liquidsonics.cinematic-rooms.professional", f"{_BASE}/cinematic-rooms/"),
    "cinematic_rooms":              ("Cinematic Rooms",              "com.liquidsonics.cinematic-rooms",              f"{_BASE}/cinematic-rooms/"),
    "seventh_heaven_professional":  ("Seventh Heaven Professional",  "com.liquidsonics.SeventhHeaven_Professional",   f"{_BASE}/seventh-heaven-professional/"),
    "seventh_heaven":               ("Seventh Heaven",               "com.liquidsonics.SeventhHeaven",                f"{_BASE}/seventh-heaven/"),
    "lustrous_plates_surround":     ("Lustrous Plates Surround",     "com.liquidsonics.LustrousPlatesSurround",       f"{_BASE}/lustrous-plates-surround/"),
    "lustrous_plates":              ("Lustrous Plates",              "com.liquidsonics.LustrousPlates",               f"{_BASE}/lustrous-plates/"),
    "illusion":                     ("Illusion",                     "com.liquidsonics.Illusion",                     f"{_BASE}/illusion/"),
    "reverberate":                  ("Reverberate 3",                "com.liquidsonics.Reverberate3",                 f"{_BASE}/reverberate-3/"),
    "tai_chi_lite":                 ("Tai Chi Lite",                 "com.liquidsonics.TaiChiLite",                   f"{_BASE}/tai-chi/"),
    "tai_chi":                      ("Tai Chi",                      "com.liquidsonics.TaiChi",                       f"{_BASE}/tai-chi/"),
    "hd_cart":                      ("HD Cart",                      "com.liquidsonics.HDCart",                       f"{_BASE}/hd-cart/"),
    "m7_link":                      ("M7 Link",                      "com.liquidsonics.M7Link",                       f"{_BASE}/m7-link/"),
}

URL_PATTERN = re.compile(
    r'https?://www\.liquidsonics\.com/dl/serve\.php\?link=[^"\'<>\s]+\.pkg',
    re.IGNORECASE,
)
FILE_PATTERN = re.compile(
    r"/(?P<slug>[A-Za-z][A-Za-z0-9_-]+?)[-_]v(?P<v>\d+(?:\.\d+){1,3})-macOS\.pkg",
)


class LiquidSonicsScraper:
    name = "liquidsonics"
    vendor = VENDOR
    homepage = "https://www.liquidsonics.com/"
    trusted_domain = "liquidsonics.com"
    # Downloads go through www.liquidsonics.com/dl/serve.php (a redirector on
    # the trusted domain), so no extra hosts are needed.
    allowed_download_hosts: list[str] = []

    def scrape(self) -> Iterable[ScrapedRelease]:
        html = fetch(DOWNLOADS_URL)
        seen: set[str] = set()
        for url in URL_PATTERN.findall(html):
            m = FILE_PATTERN.search(url)
            if not m:
                continue
            slug = m.group("slug").lower()
            # Match longest known prefix so cinematic_rooms_professional wins over cinematic_rooms.
            best: tuple[int, str] | None = None
            for key in KNOWN:
                if slug.startswith(key) and (best is None or len(key) > best[0]):
                    best = (len(key), key)
            if best is None:
                continue
            key = best[1]
            if key in seen:
                continue
            seen.add(key)
            display_name, bundle_id, product_page = KNOWN[key]
            yield ScrapedRelease(
                bundle_id=bundle_id,
                name=display_name,
                vendor=VENDOR,
                latest_version=m.group("v"),
                download_url=url,
                vendor_page=product_page,
            )
        log.info("liquidsonics: %d releases", len(seen))
