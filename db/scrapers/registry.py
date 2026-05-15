"""Registers every implemented scraper. Importing this module is enough to discover them."""
from __future__ import annotations

from .base import Scraper
from .klevgrand import KlevgrandScraper
from .liquidsonics import LiquidSonicsScraper
from .oeksound import OeksoundScraper
from .soundradix import SoundRadixScraper


def all_scrapers() -> list[Scraper]:
    return [
        SoundRadixScraper(),
        OeksoundScraper(),
        LiquidSonicsScraper(),
        KlevgrandScraper(),
    ]
