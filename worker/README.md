# plupdate-submit (Cloudflare Worker)

Single-purpose relay that turns a POST from the Plupdate macOS app into a
GitHub Issue in your **private** `plupdate-submissions` triage repo.

```
Plupdate.app  →  POST /submit  →  Worker  →  GitHub Issues API  →  private repo
```

Why this exists: GitHub doesn't let unauthenticated strangers file issues in a
private repo, and the public-data repo is searchable, so we don't want raw
user submissions landing there. This Worker is the smallest possible piece of
infrastructure that gives you screening before things become public.

## Endpoints

- **`POST /submit`** — accepts the same JSON shape the Swift app sends today:
  ```json
  {
    "clientVersion": "Plupdate/0.1.0",
    "submissions": [
      {
        "bundleId": "...",
        "name": "...",
        "observedVersion": "...",
        "vendor":      "...",   // optional
        "vendorPage":  "...",   // optional
        "downloadURL": "...",   // optional
        "notes":       "..."    // optional
      }
    ]
  }
  ```
  Returns `201 { accepted, issue }` on success.

- **`GET /health`** — `200 { status: "ok" }`. Useful for monitoring.

## Security model

- HTTPS terminated by Cloudflare.
- Per-IP rate limiting (10 req / 60s) via Workers KV. Cheap and effective for
  the volume this app produces.
- Source IP is **hashed** (SHA-256, first 6 bytes) before being written into
  the issue body, so you can spot spam patterns without storing IPs.
- The PAT (`GITHUB_TOKEN`) is a Cloudflare Worker secret, never in source.
  Scope it to **fine-grained, Issues:write only, on the submissions repo only**.

## Deploy (one-time setup)

You need: a Cloudflare account (free tier fine), a GitHub account, and
`npx` available locally.

### 1. Create the private submissions repo

On GitHub, create a **private** repo named `plupdate-submissions`. Empty is
fine — issues don't need code. Add an `issue-templates/submission.md` later if
you want to standardize.

### 2. Mint a fine-grained GitHub PAT

1. GitHub → Settings → Developer settings → Personal access tokens → **Fine-grained tokens** → Generate new token.
2. Resource owner: your account.
3. Repository access: **Only select repositories** → `plupdate-submissions`.
4. Permissions → Repository permissions → **Issues: Read and write**.
5. Set expiration as you prefer (90 days reasonable; calendar a renewal).
6. Copy the token. It starts with `github_pat_…`.

### 3. Install the worker tooling

```bash
cd worker/
npm install
npx wrangler login
```

### 4. Create the KV namespace for rate-limiting

```bash
npx wrangler kv namespace create RATE_LIMIT
```

It prints something like:

```
🌀 Creating namespace with title "plupdate-submit-RATE_LIMIT"
✨ Success!
[[kv_namespaces]]
binding = "RATE_LIMIT"
id = "abc123…"
```

Paste that `id` into `wrangler.toml`, replacing `REPLACE_WITH_KV_NAMESPACE_ID`.

### 5. Set the GITHUB_REPO and GITHUB_TOKEN

In `wrangler.toml`, replace `REPLACE_WITH_OWNER/plupdate-submissions` with
your actual `<owner>/plupdate-submissions`.

Then store the token as a Worker secret:

```bash
npx wrangler secret put GITHUB_TOKEN
# paste the github_pat_… value when prompted
```

### 6. Deploy

```bash
npx wrangler deploy
```

You'll get a URL like `https://plupdate-submit.<account>.workers.dev`.
Hit `/health` to confirm:

```bash
curl https://plupdate-submit.<account>.workers.dev/health
# {"status":"ok"}
```

### 7. Wire the app to the Worker

Edit `Sources/Plupdate/Endpoints.swift`:

```swift
static let submitURL = URL(
    string: "https://plupdate-submit.<account>.workers.dev/submit"
)!
```

Optionally add a custom domain in the Cloudflare dashboard
(`submit.plupdate.dev`) and use that instead.

## Smoke test

```bash
curl -sX POST https://plupdate-submit.<account>.workers.dev/submit \
  -H 'content-type: application/json' \
  -d '{
    "clientVersion": "test/0.0",
    "submissions": [
      { "bundleId": "test.example", "name": "Test", "observedVersion": "1.0" }
    ]
  }'
```

You should get back `{"accepted":1,"issue":N}` and a new issue should appear
in your private `plupdate-submissions` repo.

## Local development

```bash
npx wrangler dev
```

Without secrets set in dev, the GitHub call will fail with `502 upstream
failure` — that's expected. To dev against the real API, create a
`.dev.vars` file (gitignored):

```
GITHUB_TOKEN=github_pat_xxx
```

and `wrangler dev` will pick it up.
