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
CLASSIFICATION_FILE = ROOT / ".scrape-classification.json"

# A diff is a "bump" if and only if each per-plugin change touches only
# these keys; anything else (added/removed plugin, vendor name change, DRM
# change, notes/vendorPage change) counts as structural and requires human
# review.
BUMP_KEYS = {"latestVersion", "downloadURL"}

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("scrape")


def _normalize_url(u):
    # Percent-encode spaces etc. so Swift's URL(string:) accepts the value.
    return requests.utils.requote_uri(u) if u else None


# --- vendor files ---------------------------------------------------------

def vendor_payload(scraper, releases: list) -> dict:
    payload: dict = {
        "vendor": scraper.vendor,
        "homepage": scraper.homepage,
        "trustedDomain": scraper.trusted_domain,
    }
    allowed = list(getattr(scraper, "allowed_download_hosts", []) or [])
    if allowed:
        payload["allowedDownloadHosts"] = allowed
    team_id = getattr(scraper, "signing_team_id", None)
    if team_id:
        payload["signingTeamId"] = team_id
    payload["plugins"] = [
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
        ]
    return payload


def write_vendor_file(scraper, releases: list, dry_run: bool) -> str:
    """Write the vendor file and return a classification of the change.

    Returns one of: "bumps", "structural", "unchanged".
    """
    payload = vendor_payload(scraper, releases)
    path = VENDORS_DIR / f"{scraper.name}.json"
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    old_text = path.read_text(encoding="utf-8") if path.exists() else None
    classification = classify_vendor_change(old_text, text)
    if dry_run:
        log.info("--- %s (dry run, %s) ---\n%s", path, classification, text)
        return classification
    VENDORS_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    log.info(
        "wrote %s (%d plugins, %s)",
        path.relative_to(ROOT),
        len(payload["plugins"]),
        classification,
    )
    return classification


def classify_vendor_change(old_text, new_text: str) -> str:
    if old_text is None:
        return "structural"
    if old_text == new_text:
        return "unchanged"
    try:
        old = json.loads(old_text)
        new = json.loads(new_text)
    except json.JSONDecodeError:
        return "structural"
    return classify_payload_diff(old, new)


def classify_payload_diff(old: dict, new: dict) -> str:
    if old.get("vendor") != new.get("vendor"):
        return "structural"
    if old.get("homepage") != new.get("homepage"):
        return "structural"

    old_by_id = {p["bundleId"]: p for p in old.get("plugins", [])}
    new_by_id = {p["bundleId"]: p for p in new.get("plugins", [])}
    if set(old_by_id) != set(new_by_id):
        return "structural"

    for bid, op in old_by_id.items():
        np = new_by_id[bid]
        if op == np:
            continue
        differing = {k for k in set(op) | set(np) if op.get(k) != np.get(k)}
        if not differing.issubset(BUMP_KEYS):
            return "structural"
    return "bumps"


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
    classifications: dict[str, list[str]] = {"bumps": [], "structural": [], "unchanged": []}
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
        kind = write_vendor_file(s, releases, args.dry_run)
        classifications.setdefault(kind, []).append(s.name)

    if not args.dry_run:
        # Index changes (slug add/remove) are structural; updatedAt alone is fine.
        # Detect by comparing the set of slugs before/after.
        old_slugs = _read_index_slugs()
        write_index()
        new_slugs = _read_index_slugs()
        if old_slugs != new_slugs:
            classifications["structural"].append("__index__")
        _write_classification(classifications)
    return 1 if failures else 0


def _read_index_slugs() -> set[str]:
    if not INDEX_FILE.exists():
        return set()
    try:
        data = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
        return set(data.get("vendors", []))
    except json.JSONDecodeError:
        return set()


def _write_classification(classifications: dict) -> None:
    payload = {
        "bumps": sorted(classifications.get("bumps", [])),
        "structural": sorted(classifications.get("structural", [])),
        "unchanged": sorted(classifications.get("unchanged", [])),
    }
    CLASSIFICATION_FILE.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    log.info(
        "classification: bumps=%d structural=%d unchanged=%d",
        len(payload["bumps"]),
        len(payload["structural"]),
        len(payload["unchanged"]),
    )


if __name__ == "__main__":
    sys.exit(main())
