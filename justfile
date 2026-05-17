# plupdate-db dev workflows. Run `just` to list recipes.

set shell := ["bash", "-cu"]

default:
    @just --list

# --- data ---

# Run all scrapers (or one with --only=<slug>) and refresh vendors/*.json.
[group: 'data']
scrape *args:
    cd db && python -m scripts.scrape {{args}}

# Validate every vendors/*.json against schema.json + cross-file invariants.
[group: 'data']
validate:
    cd db && python scripts/validate.py

# Rebuild vendors/index.json from on-disk slugs (sorted, set-equal).
[group: 'data']
build-index:
    cd db && python -m scripts.scrape --index-only

# --- scaffold ---

# Scaffold a new vendor scraper via Claude. Pass a URL, slug, or
# plupdate-submissions issue number. Examples:
#   just scaffold-vendor https://exampleco.com/
#   just scaffold-vendor 42
#   just scaffold-vendor exampleco --reason=stalled
#
# Auth: uses `claude --print` (Claude Code CLI) if available, otherwise
# falls back to the Anthropic API (set ANTHROPIC_API_KEY in env).
[group: 'scaffold']
scaffold-vendor INPUT *flags:
    python scripts/scaffold_vendor.py {{INPUT}} {{flags}}

# Same flow but framed as "the existing scraper looks broken — make a
# new one." Adds context to the prompt about what's stale/drifting.
[group: 'scaffold']
scaffold-scraper SLUG *flags:
    python scripts/scaffold_vendor.py {{SLUG}} --reason=stalled {{flags}}

# Dry-run: print the prompt that would go to the model, don't call it.
[group: 'scaffold']
scaffold-preview INPUT:
    python scripts/scaffold_vendor.py {{INPUT}} --dry-run
