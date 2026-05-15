"""Sound Radix — public direct downloads on their website."""
from __future__ import annotations

import re
import urllib.parse
from typing import Iterable

from .base import ScrapedRelease, fetch, log

VENDOR = "Sound Radix"
DOWNLOADS_URL = "https://www.soundradix.com/downloads/"

# Map a (case-insensitive) name extracted from the installer filename to:
#   (bundle id, product page slug — under https://www.soundradix.com/products/<slug>/)
# Add entries here as more bundle ids are confirmed via user submissions.
BUNDLE_BY_NAME: dict[str, tuple[str, str]] = {
    "auto-align post":  ("com.soundradix.AutoAlignPost", "auto-align-post"),
    "muteomatic":       ("com.SoundRadix.Muteomatic",    "muteomatic"),
    "auto-align":       ("com.soundradix.AutoAlign",     "auto-align"),
    "drum leveler":     ("com.soundradix.DrumLeveler",   "drum-leveler"),
    "pi":               ("com.soundradix.Pi",            "pi"),
    "powair":           ("com.soundradix.POWAIR",        "powair"),
    "surfereq":         ("com.soundradix.SurferEQ",      "surfereq"),
    "32 lives":         ("com.soundradix.32lives",       "32-lives"),
    "radical1":         ("com.soundradix.Radical1",      "radical1"),
}

URL_PATTERN = re.compile(
    r'https?://assets\.soundradix\.com/downloads/[^"\'<>]+?\.(?:pkg|dmg)',
    re.IGNORECASE,
)
FILE_PATTERN = re.compile(r"^(?P<name>.+?)\s+v?(?P<version>\d+(?:\.\d+){1,3})", re.IGNORECASE)


class SoundRadixScraper:
    name = "soundradix"
    vendor = VENDOR
    homepage = "https://www.soundradix.com/"

    def scrape(self) -> Iterable[ScrapedRelease]:
        html = fetch(DOWNLOADS_URL)
        seen: set[str] = set()
        for raw in URL_PATTERN.findall(html):
            url = urllib.parse.unquote(raw)
            filename = url.rsplit("/", 1)[-1].rsplit(".", 1)[0]
            m = FILE_PATTERN.match(filename)
            if not m:
                continue
            display_name = m.group("name").strip()
            version = m.group("version")

            mapped: tuple[str, str] | None = None
            for key, val in BUNDLE_BY_NAME.items():
                if key in display_name.lower():
                    mapped = val
                    break
            if mapped is None or mapped[0] in seen:
                continue
            bundle_id, slug = mapped
            seen.add(bundle_id)

            yield ScrapedRelease(
                bundle_id=bundle_id,
                name=display_name,
                vendor=VENDOR,
                latest_version=version,
                download_url=raw,
                vendor_page=f"https://www.soundradix.com/products/{slug}/",
            )
        log.info("soundradix: %d releases", len(seen))
