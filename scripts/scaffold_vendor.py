#!/usr/bin/env python3
"""Scaffold a new vendor scraper + JSON via Claude.

Two auth paths:
  1. Preferred: invoke `claude --print` (uses Claude Code CLI's
     existing auth — no Anthropic API key needed).
  2. Fallback: if `claude` isn't in PATH and ANTHROPIC_API_KEY is
     set, call the API directly via db/scripts/anthropic_call.py.

Usage:
    just scaffold-vendor <url-or-slug-or-issue#>
    # or:
    python scripts/scaffold_vendor.py <url-or-slug-or-issue#> [--reason=stalled] [--hint=bundleId]

Output:
  - On success: branch `scaffold/<slug>` with new scraper + vendor JSON,
    PR opened via `gh pr create`.
  - On failure: saves the model output to `.scaffold-<slug>.patch` for
    manual inspection and exits non-zero.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

# Allow `import` from db/ tree.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "db"))


PROMPT_PATH = ROOT / "db" / "scripts" / "prompts" / "scaffold-vendor.md"
HOMEPAGE_TRUNCATE = 10_000  # chars
PREP_ENDPOINT_DEFAULT = os.environ.get("PLUPDATE_WORKER_BASE", "")


def _slug_from_input(arg: str) -> str:
    """Turn a URL / issue#'/slug into a vendor slug."""
    if arg.startswith("http"):
        host = urlparse(arg).hostname or ""
        # Strip leading www. and the TLD. "klevgrand.com" -> "klevgrand"
        h = re.sub(r"^www\.", "", host)
        h = h.split(".")[0] or "vendor"
        return re.sub(r"[^a-z0-9-]", "", h.lower()) or "vendor"
    if arg.lstrip("#").isdigit():
        return f"issue-{arg.lstrip('#')}"
    return re.sub(r"[^a-z0-9-]", "", arg.lower()) or "vendor"


def _fetch_homepage(url: str) -> str:
    """Pull and truncate raw HTML — no JS rendering, no auth."""
    import requests
    r = requests.get(url, timeout=30, headers={
        "User-Agent": "PlupdateScaffold/0.1 (+https://github.com/bootlegcheeseburger/plupdate-db)",
    })
    r.raise_for_status()
    return r.text[:HOMEPAGE_TRUNCATE]


def _scaffold_prep(url: str) -> dict:
    """Call the Worker's /admin/scaffold-prep endpoint (Step 5) if
    PLUPDATE_WORKER_BASE is configured; otherwise return a minimal
    locally-computed candidate map.
    """
    if PREP_ENDPOINT_DEFAULT:
        import requests
        try:
            r = requests.get(
                f"{PREP_ENDPOINT_DEFAULT}/admin/scaffold-prep",
                params={"url": url},
                timeout=30,
            )
            if r.ok:
                return r.json()
        except Exception as e:
            print(f"warning: prep endpoint failed ({e}); falling back to local probe", file=sys.stderr)
    # Local fallback: tiny detector running in this process.
    return _local_prep(url)


def _local_prep(url: str) -> dict:
    """Lightweight client-side strategy detection — no Worker required."""
    try:
        html = _fetch_homepage(url)
    except Exception as e:
        return {"url": url, "error": str(e), "candidates": {}}
    cand: dict = {"sparkle": None, "jsonld": [], "sitemap": None, "rss": None}
    # JSON-LD blocks
    for m in re.finditer(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, re.IGNORECASE | re.DOTALL,
    ):
        try:
            cand["jsonld"].append(json.loads(m.group(1).strip()))
        except json.JSONDecodeError:
            pass
    # Appcast / RSS / sitemap link hints
    for href in re.findall(r'href=["\']([^"\'>]+\.(?:xml|atom))["\']', html, re.IGNORECASE):
        low = href.lower()
        if "appcast" in low:  cand["sparkle"] = href
        elif "rss" in low or "feed" in low: cand["rss"] = href
        elif "sitemap" in low: cand["sitemap"] = href
    return {"url": url, "fetchedAt": None, "candidates": cand, "rawHtmlSample": html[:8000]}


def _build_prompt(template: str, *, input_context: str, candidates: dict, html_sample: str) -> str:
    return (template
        .replace("{INPUT_CONTEXT}", input_context)
        .replace("{CANDIDATES_JSON}", json.dumps(candidates, indent=2))
        .replace("{HOMEPAGE_HTML}", html_sample)
    )


def _call_model(prompt: str, *, model: str | None = None) -> str:
    """Try claude CLI first, then Anthropic API."""
    claude = shutil.which("claude")
    if claude:
        print(f"using claude CLI ({claude})", file=sys.stderr)
        proc = subprocess.run(
            [claude, "--print"] + (["--model", model] if model else []),
            input=prompt, capture_output=True, text=True, timeout=300,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"claude CLI failed: {proc.stderr[:500]}")
        return proc.stdout
    # Fallback: API
    print("claude CLI not found; falling back to Anthropic API", file=sys.stderr)
    from anthropic_call import call_anthropic, DEFAULT_MODEL  # noqa
    return call_anthropic(prompt, model=model or DEFAULT_MODEL)


def _apply_diff_to_branch(diff_text: str, slug: str) -> bool:
    """Create branch, git apply, return True if applied cleanly."""
    branch = f"scaffold/{slug}"
    # Branch from current HEAD.
    subprocess.run(["git", "checkout", "-b", branch], cwd=ROOT, check=True)
    proc = subprocess.run(
        ["git", "apply", "--3way"], input=diff_text, text=True,
        cwd=ROOT, capture_output=True,
    )
    if proc.returncode != 0:
        patch_path = ROOT / f".scaffold-{slug}.patch"
        patch_path.write_text(diff_text, encoding="utf-8")
        print(f"git apply failed; saved diff to {patch_path}", file=sys.stderr)
        print(proc.stderr, file=sys.stderr)
        return False
    return True


def _run_validator() -> bool:
    proc = subprocess.run(
        ["python", "db/scripts/validate.py"],
        cwd=ROOT, capture_output=True, text=True,
    )
    print(proc.stdout, file=sys.stderr)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="vendor URL, plupdate-submissions issue#, or slug")
    ap.add_argument("--reason", default="new", help="invocation reason (new | stalled | drift)")
    ap.add_argument("--hint", default=None, help="bundleId hint (drift case)")
    ap.add_argument("--model", default=None, help="claude / API model override")
    ap.add_argument("--dry-run", action="store_true",
                    help="print prompt + model output without applying diff or opening PR")
    args = ap.parse_args()

    slug = _slug_from_input(args.input)
    # Resolve a homepage URL from the input.
    url = args.input if args.input.startswith("http") else f"https://{slug}.com"

    print(f"scaffold-vendor: slug={slug} url={url} reason={args.reason}", file=sys.stderr)

    prep = _scaffold_prep(url)
    template = PROMPT_PATH.read_text(encoding="utf-8")
    input_context = json.dumps({
        "rawInput": args.input,
        "resolvedSlug": slug,
        "resolvedUrl": url,
        "reason": args.reason,
        "hint": args.hint,
    }, indent=2)
    html_sample = prep.get("rawHtmlSample") or _fetch_homepage(url)[:HOMEPAGE_TRUNCATE]
    prompt = _build_prompt(
        template,
        input_context=input_context,
        candidates=prep.get("candidates", {}),
        html_sample=html_sample[:HOMEPAGE_TRUNCATE],
    )

    if args.dry_run:
        print("--- PROMPT ---")
        print(prompt[:4000])
        print("--- ... (truncated) ---")
        return 0

    print("calling model — this can take ~30s", file=sys.stderr)
    diff = _call_model(prompt, model=args.model)
    if not diff.lstrip().startswith("diff --git"):
        patch_path = ROOT / f".scaffold-{slug}.patch"
        patch_path.write_text(diff, encoding="utf-8")
        print(f"model didn't return a unified diff; saved raw output to {patch_path}", file=sys.stderr)
        return 1

    if not _apply_diff_to_branch(diff, slug):
        return 1

    print("running validator", file=sys.stderr)
    if not _run_validator():
        print("validator failed — leaving branch checked out for manual fixes", file=sys.stderr)
        return 1

    # Open PR via gh.
    title = f"scaffold: add {slug} ({args.reason})"
    body = (
        f"Scaffolded via `just scaffold-vendor {args.input}`.\n\n"
        f"- reason: `{args.reason}`\n"
        f"- input: `{args.input}`\n"
        f"- model: `{args.model or 'default'}`\n"
        f"\nReview the scraper before merging — this is a starting point, "
        "not a finished product. Confirm bundle IDs against installed binaries."
    )
    proc = subprocess.run(
        ["gh", "pr", "create", "--title", title, "--body", body],
        cwd=ROOT, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        print("gh pr create failed:", proc.stderr, file=sys.stderr)
        print("branch is ready; push + open the PR manually", file=sys.stderr)
        return 1
    print(proc.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
