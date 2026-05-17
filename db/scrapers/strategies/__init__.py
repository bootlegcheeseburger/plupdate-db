"""Reusable version-extraction strategies for vendor scrapers.

Each strategy is a single callable that fetches some upstream resource
(JSON manifest, Sparkle appcast, JSON-LD-tagged HTML, sitemap, GitHub
releases feed, or a raw URL probed with a regex) and yields
ScrapedRelease objects. Strategies fail loudly via `StrategyMiss` when
the expected shape isn't present; the runner records that outcome in
the structured scrape log so a "tried jsonld, got nothing" trail is
visible without being noisy in PRs.

New vendor scrapers should declare a strategy (or compose two) instead
of hand-rolling HTML parsing. Existing hand-rolled scrapers continue to
work — strategies are an addition, not a forced migration.

See db/CONTRIBUTING.md "Choosing a strategy" for guidance.
"""
from __future__ import annotations


class StrategyMiss(Exception):
    """Raised when a strategy can't extract the data it expects.

    Signals "I looked, the shape wasn't there" — distinct from network
    errors (which propagate as the underlying exception). The runner
    catches this to record a structured miss in the scrape log without
    failing the whole vendor's scrape.
    """


# Public re-exports so callers can `from strategies import regex` etc.
from .manifest import manifest               # noqa: E402
from .appcast import appcast                 # noqa: E402
from .jsonld import jsonld                   # noqa: E402
from .sitemap import sitemap                 # noqa: E402
from .github_releases import github_releases # noqa: E402
from .regex import regex_extract             # noqa: E402

STRATEGIES = {
    "manifest": manifest,
    "appcast": appcast,
    "jsonld": jsonld,
    "sitemap": sitemap,
    "github_releases": github_releases,
    "regex": regex_extract,
}

__all__ = ["STRATEGIES", "StrategyMiss", "manifest", "appcast", "jsonld", "sitemap", "github_releases", "regex_extract"]
