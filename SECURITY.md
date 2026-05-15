# Security Policy

## Reporting a vulnerability

Please do not open a public GitHub issue for security problems.

Use GitHub's private advisory channel:
[Report a vulnerability](../../security/advisories/new)

Or email: dan@dantimmons.net

I aim to acknowledge reports within 72 hours. As a solo maintainer, fix
turnaround depends on severity and availability.

## Scope

This repository is a versioned data snapshot consumed by the `plupdate`
tooling. The likely "security" issues are:

- **Bad or malicious data** (incorrect plugin metadata, hostile URLs in
  records) - report via private advisory or email; do not file public
  issues that re-publish the suspect content.
- **Repository-level concerns** (account compromise, broken trust chain
  on signed commits) - use the advisory channel above.

Specific gates we'd want to know about if you can bypass them:

- **`trustedDomain` host enforcement** in `db/scripts/validate.py` —
  every `vendorPage` / `downloadURL` is required to be on the vendor's
  declared trusted domain (or a subdomain), or on the vendor's
  `allowedDownloadHosts` allowlist.
- **`trustedDomain` change-lock** — silent domain changes on existing
  vendor files are refused unless a maintainer applies the
  `domain-change-reviewed` label.
- **Unicode hygiene** — vendor / plugin name / notes fields reject bidi
  overrides (U+202A-E, U+2066-9), zero-width chars (U+200B-D, U+FEFF,
  U+180E), and C0/C1 controls. A working homoglyph or RLO attack
  against displayed strings is in scope.
- **Schema bypass** — getting a vendor file past `validate.py` in a
  shape the app then mis-renders or trusts incorrectly.

Out of scope:

- Bugs in the `plupdate` app itself - report at the `plupdate` repo.
- Third-party dependencies (report upstream).
