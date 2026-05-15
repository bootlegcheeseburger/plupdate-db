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

Out of scope:

- Bugs in the `plupdate` app itself - report at the `plupdate` repo.
- Third-party dependencies (report upstream).
