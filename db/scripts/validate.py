"""Validate every vendors/*.json against schema.json + cross-file invariants.

Used by CI on every PR. Enforces:
- vendor files match schema.json
- bundleIds unique within and across files
- vendors/index.json lists exactly the slugs present on disk, sorted
- each vendor file's filename matches its slug
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

try:
    from jsonschema import Draft202012Validator
except ImportError:
    print("error: pip install jsonschema", file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).resolve().parent.parent
VENDORS_DIR = ROOT / "vendors"
SCHEMA_FILE = ROOT / "schema.json"
INDEX_FILE = VENDORS_DIR / "index.json"

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("validate")


# --- trustedDomain change-lock --------------------------------------------

def _check_trusted_domain_stability(name: str, slug: str, data: dict) -> int:
    """Refuse silent changes to an existing vendor's trustedDomain.

    Compares against the version of the file on PLUPDATE_BASE_REF (the
    workflow points this at origin/<base> on PRs and HEAD~1 on direct pushes).
    Skipped when PLUPDATE_BASE_REF is unset (e.g., local runs) or when
    PLUPDATE_ALLOW_DOMAIN_CHANGE=1 is explicitly set (CI: add the
    `domain-change-reviewed` label to the PR).
    """
    if os.environ.get("PLUPDATE_ALLOW_DOMAIN_CHANGE") == "1":
        return 0
    base_ref = os.environ.get("PLUPDATE_BASE_REF")
    if not base_ref:
        return 0
    try:
        result = subprocess.run(
            ["git", "show", f"{base_ref}:db/vendors/{name}"],
            capture_output=True, text=True, check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return 0  # file isn't on base ref — brand new vendor file, allowed
    try:
        old = json.loads(result.stdout)
    except json.JSONDecodeError:
        return 0
    old_td = old.get("trustedDomain")
    new_td = data.get("trustedDomain")
    if old_td and new_td and old_td != new_td:
        log.error(
            "%s: trustedDomain changed from %r to %r. Domain changes are "
            "rare and high-stakes. If intentional, add the "
            "`domain-change-reviewed` label to the PR (CI will then set "
            "PLUPDATE_ALLOW_DOMAIN_CHANGE=1) before merging.",
            name, old_td, new_td,
        )
        return 1
    return 0


# --- unicode hygiene -------------------------------------------------------

# Bidi overrides + isolates: can render a string differently than its bytes.
_BIDI_CHARS = {chr(c) for c in (
    0x202A, 0x202B, 0x202C, 0x202D, 0x202E,
    0x2066, 0x2067, 0x2068, 0x2069,
)}
# Zero-width chars: invisible, useful for homoglyph attacks.
_ZERO_WIDTH = {chr(c) for c in (0x200B, 0x200C, 0x200D, 0xFEFF, 0x180E)}
# C0/C1 control ranges + DEL.
_CONTROL = {chr(c) for c in range(0x00, 0x20)} | {chr(0x7F)} | {chr(c) for c in range(0x80, 0xA0)}

# Single-line fields disallow tab/LF/CR too.
_BAD_SINGLE_LINE = _BIDI_CHARS | _ZERO_WIDTH | _CONTROL
# Multi-line fields keep tab/LF/CR.
_BAD_MULTI_LINE = _BAD_SINGLE_LINE - {"\t", "\n", "\r"}


def _check_unicode_hygiene(name: str, data: dict) -> int:
    errors = 0
    errors += _check_string(name, "vendor", data.get("vendor"), _BAD_SINGLE_LINE)
    for i, p in enumerate(data.get("plugins", [])):
        loc = f"plugins/{i} ({p.get('bundleId', '?')})"
        errors += _check_string(name, f"{loc}.name", p.get("name"), _BAD_SINGLE_LINE)
        errors += _check_string(name, f"{loc}.notes", p.get("notes"), _BAD_MULTI_LINE)
    return errors


def _check_string(file: str, loc: str, value, banned: set) -> int:
    if not isinstance(value, str) or not value:
        return 0
    found = sorted({hex(ord(c)) for c in value if c in banned})
    if found:
        log.error(
            "%s: %s contains disallowed character(s): %s "
            "(control / bidi / zero-width — likely an attempt to deceive)",
            file, loc, ", ".join(found),
        )
        return 1
    return 0


# --- URL security ---------------------------------------------------------

def _host_matches_domain(host: str, domain: str) -> bool:
    """True if host equals domain or is a proper subdomain.

    Uses suffix match anchored on a leading '.' so 'evilfoo.com' does not
    match 'foo.com'.
    """
    h = host.lower()
    d = domain.lower()
    return h == d or h.endswith("." + d)


def _check_url_security(name: str, data: dict) -> int:
    """Enforce that homepage and every vendorPage is on the trusted host."""
    trusted = data.get("trustedDomain")
    homepage = data.get("homepage")

    errors = 0

    if not trusted:
        # schema check will already have flagged this; nothing more to do.
        return 0

    # Homepage, if present, must live on the trusted domain.
    if homepage:
        try:
            u = urlparse(homepage)
        except Exception as e:
            log.error("%s: homepage parse error: %s", name, e)
            return 1
        if u.scheme != "https":
            log.error("%s: homepage must use https:// — got %r", name, homepage)
            errors += 1
        if u.hostname and not _host_matches_domain(u.hostname, trusted):
            log.error(
                "%s: homepage host %r is not on trustedDomain %r",
                name, u.hostname, trusted,
            )
            errors += 1

    for i, p in enumerate(data.get("plugins", [])):
        loc = f"plugins/{i} ({p.get('bundleId', '?')})"

        vp = p.get("vendorPage")
        if vp:
            errors += _check_vendor_page_url(name, loc, vp, trusted)

        # source.url has the same host requirements as vendorPage: must
        # live on the trusted domain (or, for portal vendors, an
        # allowedDownloadHosts entry — same exception as vendorPage).
        src = p.get("source")
        if isinstance(src, dict):
            su = src.get("url")
            if su:
                errors += _check_vendor_page_url(
                    name, f"{loc}.source.url", su, trusted,
                )

    return errors


def _check_vendor_page_url(name: str, loc: str, url: str, trusted: str) -> int:
    try:
        u = urlparse(url)
    except Exception as e:
        log.error("%s: %s: vendorPage parse error: %s", name, loc, e)
        return 1
    errors = 0
    if u.scheme != "https":
        log.error("%s: %s: vendorPage must use https:// — got %r", name, loc, url)
        errors += 1
    host = u.hostname or ""
    if not _host_matches_domain(host, trusted):
        log.error(
            "%s: %s: vendorPage host %r is not on trustedDomain %r",
            name, loc, host, trusted,
        )
        errors += 1
    return errors


# --- distribution / portal coherence -------------------------------------

SCRAPERS_DIR = ROOT / "scrapers"


def _check_distribution(name: str, slug: str, data: dict) -> int:
    """Distribution mode must align with scraper presence + portal metadata.

    - "scraper" (or omitted): db/scrapers/<slug>.py MUST exist.
    - "portal": data.portal MUST exist. A scraper is OPTIONAL — many
        portal-distributed vendors still publish changelogs or product
        pages worth a best-effort scrape (used as supplementary signal;
        the portal app remains canonical).
    - "manual": db/scrapers/<slug>.py MUST NOT exist (the maintainer
        tracks updates by hand; no automation expected).

    Refuses portal vendors that forget to declare which portal app users
    need, and orphan scraper files on manual-tracked vendors.
    """
    dist = data.get("distribution") or "scraper"
    scraper_file = SCRAPERS_DIR / f"{slug}.py"
    has_scraper = scraper_file.exists()
    errors = 0
    if dist == "scraper":
        if not has_scraper:
            log.error(
                "%s: distribution='scraper' (or omitted) but %s does not exist. "
                "Either add a scraper or set distribution to 'portal'/'manual'.",
                name, scraper_file.relative_to(ROOT.parent),
            )
            errors += 1
    elif dist == "manual":
        if has_scraper:
            log.error(
                "%s: distribution='manual' but %s still exists. "
                "Remove the orphan scraper file or switch distribution to 'scraper' / 'portal'.",
                name, scraper_file.relative_to(ROOT.parent),
            )
            errors += 1
    elif dist == "portal":
        if not data.get("portal"):
            log.error(
                "%s: distribution='portal' requires a 'portal' object with at "
                "least a 'name' field (e.g. 'iZotope Product Portal').",
                name,
            )
            errors += 1
        # A scraper is allowed (best-effort supplementary signal) — no
        # error either way.
    return errors


def main() -> int:
    schema = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)

    errors = 0
    seen_bundles: dict[str, str] = {}
    slugs_on_disk: list[str] = []

    # Skip the index and any `_*.json` (reserved for templates like _sample.json).
    files = sorted(
        p for p in VENDORS_DIR.glob("*.json")
        if p.name != "index.json" and not p.name.startswith("_")
    )
    if not files:
        log.warning("no vendor files in %s", VENDORS_DIR)

    for f in files:
        slugs_on_disk.append(f.stem)
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            log.error("%s: invalid JSON: %s", f.name, e)
            errors += 1
            continue

        for err in validator.iter_errors(data):
            path = "/".join(str(p) for p in err.absolute_path) or "<root>"
            log.error("%s: %s — %s", f.name, path, err.message)
            errors += 1

        bundles_in_file: set[str] = set()
        for p in data.get("plugins", []):
            bid = p.get("bundleId")
            if not bid:
                continue
            if bid in bundles_in_file:
                log.error("%s: duplicate bundleId within file: %s", f.name, bid)
                errors += 1
            bundles_in_file.add(bid)
            if bid in seen_bundles and seen_bundles[bid] != f.name:
                log.error("%s: bundleId %s also in %s", f.name, bid, seen_bundles[bid])
                errors += 1
            else:
                seen_bundles[bid] = f.name

        errors += _check_url_security(f.name, data)
        errors += _check_trusted_domain_stability(f.name, f.stem, data)
        errors += _check_unicode_hygiene(f.name, data)
        errors += _check_distribution(f.name, f.stem, data)

    # vendors/_sample.json — schema-only check so contributors copying from a
    # broken template don't waste their time. Excluded from uniqueness checks
    # and from the index (the leading underscore reserves it as a template).
    sample = VENDORS_DIR / "_sample.json"
    if sample.exists():
        try:
            data = json.loads(sample.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            log.error("%s: invalid JSON: %s", sample.name, e)
            errors += 1
        else:
            for err in validator.iter_errors(data):
                path = "/".join(str(p) for p in err.absolute_path) or "<root>"
                log.error("%s: %s — %s", sample.name, path, err.message)
                errors += 1

    # vendors/index.json — set equality with on-disk slugs, sorted.
    if not INDEX_FILE.exists():
        log.error("vendors/index.json missing — run `python scripts/build_index.py`")
        errors += 1
    else:
        try:
            idx = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            log.error("vendors/index.json: invalid JSON: %s", e)
            errors += 1
        else:
            listed = idx.get("vendors")
            if not isinstance(listed, list) or not all(isinstance(s, str) for s in listed):
                log.error("vendors/index.json: 'vendors' must be a list of strings")
                errors += 1
            else:
                expected = sorted(slugs_on_disk)
                if listed != expected:
                    extra = set(listed) - set(expected)
                    missing = set(expected) - set(listed)
                    if extra:
                        log.error("vendors/index.json lists %s but no matching files exist", sorted(extra))
                    if missing:
                        log.error("vendors/index.json missing %s (files exist on disk)", sorted(missing))
                    if listed != expected and not extra and not missing:
                        log.error("vendors/index.json is not sorted")
                    log.error("  fix: run `python scripts/build_index.py`")
                    errors += 1

    if errors:
        log.error("%d validation error(s)", errors)
        return 1
    log.info("ok: %d vendor files, %d total plugins, index in sync", len(files), len(seen_bundles))
    return 0


if __name__ == "__main__":
    sys.exit(main())
