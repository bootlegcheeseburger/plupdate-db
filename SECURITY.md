# Security Policy

## Reporting a vulnerability

Please don't open a public issue for security problems. Instead:

- [Report a vulnerability](../../security/advisories/new) via GitHub's private advisory channel, or
- Email dan@dantimmons.net

I'll try to acknowledge within a few days. This is a solo project, so
fix timing depends on severity and how busy life is.

## What's in scope

This repo holds versioned plugin data consumed by the `plupdate` app.
Things worth flagging:

- Bad or malicious data in vendor / plugin records (hostile URLs,
  misleading metadata).
- Ways to slip something past `db/scripts/validate.py` that the app
  then trusts or mis-renders.
- Repo-level concerns (account compromise, signing issues).

## Out of scope

- Bugs in the `plupdate` app itself - report those on the app repo.
- Third-party dependencies - report upstream.

Thanks for taking the time to look.
