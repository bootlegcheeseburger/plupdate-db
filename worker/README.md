# plupdate-submit

Cloudflare Worker that relays user submissions from the Plupdate macOS
app to GitHub Issues in a private triage repo.

```
Plupdate.app -> POST /submit -> Worker -> Issues API -> private repo
```

## Endpoints

- `POST /submit` - accepts the JSON shape the Swift app sends.
  Returns `201 { accepted, issue }`.
- `GET /health` - returns `200 { status: "ok" }`.

## Deploy

Maintainer-only. Required: a Cloudflare account, a fine-grained GitHub
PAT scoped to Issues:write on the submissions repo, and a KV namespace
for rate limiting. Config lives in `wrangler.toml`; the PAT is set with
`wrangler secret put GITHUB_TOKEN`.
