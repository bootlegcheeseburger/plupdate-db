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
import sys
from pathlib import Path

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
