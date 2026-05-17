"""GitHub releases API strategy.

Rare for commercial AAX vendors but exists for open-source and
hobbyist plugins. The GH releases API returns the latest tag and
assets in a single GET — most reliable form of "version" extraction
when the upstream lives on GitHub.

No auth needed for public repos (60 req/h unauthenticated; PAT bumps
to 5000/h). The runner can pass a token via env if it's hammering
many GH-hosted vendors.
"""
from __future__ import annotations

import os
from typing import Iterable, Optional

import requests

from . import StrategyMiss
from scrapers.base import ScrapedRelease, USER_AGENT, DEFAULT_TIMEOUT


def github_releases(
    repo: str,
    *,
    bundle_id: str,
    name: Optional[str] = None,
    vendor: str,
    vendor_page: Optional[str] = None,
    asset_pattern: Optional[str] = None,
) -> Iterable[ScrapedRelease]:
    """Fetch the latest GitHub release of `owner/repo` and yield one
    ScrapedRelease.

    Args:
        repo: "owner/name" string.
        bundle_id: bundleId this repo represents.
        name: display name; falls back to release name or repo name.
        vendor: vendor display name.
        vendor_page: optional product page URL.
        asset_pattern: if set (substring match), used to pick which
            release asset becomes downloadURL (e.g. "macOS").

    Raises:
        StrategyMiss: repo has no releases, or the latest has no
            tag_name.
    """
    headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = requests.get(
        f"https://api.github.com/repos/{repo}/releases/latest",
        timeout=DEFAULT_TIMEOUT,
        headers=headers,
    )
    if r.status_code == 404:
        raise StrategyMiss(f"github_releases: {repo} has no published releases")
    r.raise_for_status()
    data = r.json()

    tag = data.get("tag_name") or data.get("name")
    if not tag:
        raise StrategyMiss(f"github_releases: {repo} latest release has no tag_name")
    # Strip leading "v" — "v1.2.3" -> "1.2.3".
    version = tag.lstrip("vV") if isinstance(tag, str) else str(tag)

    download_url = None
    if asset_pattern:
        for a in data.get("assets") or []:
            n = a.get("name") or ""
            if asset_pattern in n:
                download_url = a.get("browser_download_url")
                break

    return [ScrapedRelease(
        bundle_id=bundle_id,
        name=name or data.get("name") or repo.split("/")[-1],
        vendor=vendor,
        latest_version=version,
        download_url=download_url,
        vendor_page=vendor_page or f"https://github.com/{repo}",
    )]
