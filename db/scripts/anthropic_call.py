"""Fallback Anthropic-API caller for scaffold_vendor when `claude` CLI
is not available.

Usage:
    from anthropic_call import call_anthropic
    output = call_anthropic(prompt, model="claude-sonnet-4-6")

Reads ANTHROPIC_API_KEY from env. Uses the raw /v1/messages endpoint
via `requests` to avoid pulling in the anthropic SDK as a dependency.

Default model: claude-sonnet-4-6 (fast, cheap, good enough for
scaffolding ~50-line Python). For harder cases (regenerate-broken-
scraper), the caller can pass model="claude-opus-4-7".
"""
from __future__ import annotations

import json
import os
import sys
from typing import Optional

import requests

ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-sonnet-4-6"
ENDPOINT = "https://api.anthropic.com/v1/messages"


class AnthropicError(RuntimeError):
    pass


def call_anthropic(
    prompt: str,
    *,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 8192,
    api_key: Optional[str] = None,
    timeout: int = 120,
) -> str:
    """POST a single user message to /v1/messages and return the
    assistant's concatenated text content.

    Raises AnthropicError on auth/network/decode failure.
    """
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise AnthropicError(
            "ANTHROPIC_API_KEY not set. Either set it in env, or use the "
            "preferred path: install Claude Code CLI (`claude`) and let "
            "scaffold_vendor.sh invoke `claude --print` instead."
        )
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    headers = {
        "x-api-key": key,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }
    r = requests.post(ENDPOINT, headers=headers, data=json.dumps(payload), timeout=timeout)
    if r.status_code != 200:
        raise AnthropicError(f"anthropic api: {r.status_code} {r.text[:500]}")
    try:
        data = r.json()
    except json.JSONDecodeError as e:
        raise AnthropicError(f"anthropic api: non-JSON response: {e}") from None
    # Response shape: { content: [{type:"text", text:"..."}, ...] }
    parts = data.get("content") or []
    text_parts = [p.get("text", "") for p in parts if p.get("type") == "text"]
    if not text_parts:
        raise AnthropicError(f"anthropic api: empty content: {data}")
    return "".join(text_parts)


if __name__ == "__main__":
    # Smoke test from the shell:  python anthropic_call.py "Say hi briefly"
    if len(sys.argv) < 2:
        print("usage: anthropic_call.py <prompt>", file=sys.stderr)
        sys.exit(2)
    print(call_anthropic(sys.argv[1]))
