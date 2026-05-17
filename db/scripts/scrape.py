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

def _existing_vendor_meta(slug: str) -> dict:
    """Read fields we want to preserve across scrape runs (distribution,
    portal). The scraper itself doesn't emit these — they're maintainer-
    set, so we read them from the on-disk vendor JSON and re-emit them
    after the scrape rebuilds the file.
    """
    f = VENDORS_DIR / f"{slug}.json"
    if not f.exists():
        return {}
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    out = {}
    if "distribution" in data:
        out["distribution"] = data["distribution"]
    if "portal" in data:
        out["portal"] = data["portal"]
    return out


def _existing_plugin_sources(slug: str) -> dict[str, dict]:
    """Map of bundleId -> existing plugin dict for plugins that declare a
    `source` override. Used by the runner to honor `manual` / `skip` /
    `appcast` plugin overrides and to detect URL overrides for `scraper`
    kind. Plugins without `source` aren't in the returned map.
    """
    f = VENDORS_DIR / f"{slug}.json"
    if not f.exists():
        return {}
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    out = {}
    for p in data.get("plugins", []):
        if isinstance(p.get("source"), dict):
            out[p["bundleId"]] = p
    return out


def _release_to_plugin(r) -> dict:
    return {
        "bundleId": r.bundle_id,
        "name": r.name,
        "latestVersion": r.latest_version,
        "vendorPage": _normalize_url(r.vendor_page),
        "downloadURL": _normalize_url(r.download_url),
        "notes": r.notes,
        "drm": r.drm,
    }


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
    # Preserve maintainer-set distribution metadata across scrape runs.
    # Without this, every scrape would silently strip portal/manual
    # markers and the file would fall back to default ('scraper').
    payload.update(_existing_vendor_meta(scraper.name))

    # Per-plugin source overrides (manual / skip / scraper-with-url /
    # appcast). The runner caller passes the existing source map in via
    # scraper._plugin_source_overrides if any are applicable; we honor
    # them by either preserving the existing plugin entry or running a
    # targeted scrape_one call for URL overrides.
    overrides = getattr(scraper, "_plugin_source_overrides", {}) or {}

    by_id: dict[str, dict] = {}
    for r in releases:
        by_id[r.bundle_id] = _release_to_plugin(r)

    # Apply preserved entries for manual/skip plugins, and re-scrape
    # entries for scraper-kind URL overrides.
    for bid, existing in overrides.items():
        kind = (existing.get("source") or {}).get("kind", "scraper")
        if kind in ("manual", "skip"):
            # Keep the on-disk version verbatim; the scraper output (if
            # any) is ignored for this plugin.
            by_id[bid] = {k: existing.get(k) for k in (
                "bundleId", "name", "latestVersion", "vendorPage",
                "downloadURL", "notes", "drm",
            ) if k in existing}
        elif kind == "scraper":
            url_override = (existing.get("source") or {}).get("url")
            if url_override:
                try:
                    scrape_one = getattr(scraper, "scrape_one", None)
                    if callable(scrape_one):
                        r = scrape_one(bid, url_override)
                    else:
                        from scrapers.base import default_scrape_one
                        r = default_scrape_one(scraper, bid, url_override)
                    if r is not None:
                        by_id[bid] = _release_to_plugin(r)
                except Exception as e:
                    log.warning(
                        "%s: scrape_one(%s) failed (%s) — keeping existing entry",
                        scraper.name, bid, e,
                    )
                    by_id[bid] = {k: existing.get(k) for k in (
                        "bundleId", "name", "latestVersion", "vendorPage",
                        "downloadURL", "notes", "drm",
                    ) if k in existing}
        elif kind == "appcast":
            log.warning(
                "%s: appcast source for %s — appcast strategy not yet wired; keeping existing entry",
                scraper.name, bid,
            )
            by_id[bid] = {k: existing.get(k) for k in (
                "bundleId", "name", "latestVersion", "vendorPage",
                "downloadURL", "notes", "drm",
            ) if k in existing}

    # Re-attach `source` to plugins that had one. The scraper output
    # itself never emits `source` — it's maintainer-set metadata.
    for bid, p in by_id.items():
        if bid in overrides:
            p["source"] = overrides[bid].get("source")

    payload["plugins"] = sorted(
        by_id.values(),
        key=lambda p: (p.get("name") or "").lower(),
    )
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
        # Honor the distribution mode:
        # - "scraper" (or omitted): normal scrape, canonical source.
        # - "portal": still scrape best-effort (changelogs, backup
        #   download links) but treat output as supplementary — the
        #   portal app is canonical. We don't currently differentiate
        #   in behavior here, but log the mode so the structured scrape
        #   log (Step 3) can mark these results as supplementary.
        # - "manual": maintainer-tracked, skip entirely.
        meta = _existing_vendor_meta(s.name)
        dist = meta.get("distribution") or "scraper"
        if dist == "manual":
            log.info("%s: distribution=manual — skipping scrape", s.name)
            classifications["unchanged"].append(s.name)
            continue
        if dist == "portal":
            log.info("%s: distribution=portal — scraping best-effort (supplementary)", s.name)
        # Per-plugin source overrides are attached as a private attr on
        # the scraper instance for vendor_payload to consult. Avoids
        # changing the Scraper Protocol surface.
        s._plugin_source_overrides = _existing_plugin_sources(s.name)
        try:
            releases = list(s.scrape())
        except Exception as e:
            log.error("%s: %s", s.name, e)
            failures += 1
            continue
        # No releases is fine when every plugin in this vendor is
        # manual/skip-overridden (e.g. a portal vendor whose web scrape
        # returns nothing). The override merge will preserve existing
        # entries.
        if not releases and not s._plugin_source_overrides:
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
