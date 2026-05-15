"""Run scrapers and refresh the vendor JSON files (and vendors/index.json).

Each scraper in scrapers/registry.py emits ScrapedRelease records; we group
them by vendor and overwrite the per-vendor JSON file. The git diff after a
run *is* the changelog — no upserts, no migrations.

Usage:
    python -m scripts.scrape                      # run all scrapers + index
    python -m scripts.scrape --only oeksound      # run one scraper
    python -m scripts.scrape --dry-run            # print, write nothing
    python -m scripts.scrape --index-only         # rebuild index from disk
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests.utils

# Allow `python scripts/scrape.py` from db/ root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scrapers.registry import all_scrapers  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
VENDORS_DIR = ROOT / "vendors"
INDEX_FILE = VENDORS_DIR / "index.json"

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("scrape")


def _normalize_url(u):
    # Percent-encode spaces etc. so Swift's URL(string:) accepts the value.
    return requests.utils.requote_uri(u) if u else None


# --- vendor files ---------------------------------------------------------

def vendor_payload(scraper, releases: list) -> dict:
    return {
        "vendor": scraper.vendor,
        "homepage": scraper.homepage,
        "plugins": [
            {
                "bundleId": r.bundle_id,
                "name": r.name,
                "latestVersion": r.latest_version,
                "vendorPage": _normalize_url(r.vendor_page),
                "downloadURL": _normalize_url(r.download_url),
                "notes": r.notes,
                "drm": r.drm,
            }
            for r in sorted(releases, key=lambda r: r.name.lower())
        ],
    }


def write_vendor_file(scraper, releases: list, dry_run: bool) -> None:
    payload = vendor_payload(scraper, releases)
    path = VENDORS_DIR / f"{scraper.name}.json"
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    if dry_run:
        log.info("--- %s (dry run) ---\n%s", path, text)
        return
    VENDORS_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    log.info("wrote %s (%d plugins)", path.relative_to(ROOT), len(payload["plugins"]))


# --- index ----------------------------------------------------------------

def list_vendor_slugs() -> list[str]:
    """Vendor slugs derived from `vendors/<slug>.json` filenames, sorted.

    Skips `index.json` and any `_*.json` (reserved for templates/samples).
    """
    return sorted(
        p.stem for p in VENDORS_DIR.glob("*.json")
        if p.name != "index.json" and not p.name.startswith("_")
    )


def write_index() -> None:
    payload = {
        "vendors": list_vendor_slugs(),
        "updatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    INDEX_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    log.info("wrote %s (%d vendors)", INDEX_FILE.relative_to(ROOT), len(payload["vendors"]))


# --- CLI ------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--only", help="run a single scraper by name")
    p.add_argument("--dry-run", action="store_true", help="print, don't write")
    p.add_argument("--index-only", action="store_true",
                   help="skip scrapers; just rebuild vendors/index.json from disk")
    args = p.parse_args()

    if args.index_only:
        write_index()
        return 0

    scrapers = all_scrapers()
    if args.only:
        scrapers = [s for s in scrapers if s.name == args.only]
        if not scrapers:
            log.error("no scraper named %r", args.only)
            return 2

    failures = 0
    for s in scrapers:
        try:
            releases = list(s.scrape())
        except Exception as e:
            log.error("%s: %s", s.name, e)
            failures += 1
            continue
        if not releases:
            log.warning("%s: no releases scraped (skipping write)", s.name)
            continue
        write_vendor_file(s, releases, args.dry_run)

    if not args.dry_run:
        write_index()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
