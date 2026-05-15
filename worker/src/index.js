// Plupdate submission relay.
// POST /submit  → file an issue in the private plupdate-submissions repo.
// GET  /health  → 200 ok.
//
// Secrets (set via `wrangler secret put`):
//   GITHUB_TOKEN   - fine-grained PAT with Issues:write on the submissions repo
//   GITHUB_REPO    - "owner/repo", e.g. "dantimmons/plupdate-submissions"
//
// Bindings (in wrangler.toml):
//   RATE_LIMIT     - Workers KV namespace for IP rate-limit state

const RATE_WINDOW_MS = 60_000;
const RATE_MAX = 10;
const MAX_BODY_BYTES = 64 * 1024;
const MAX_SUBMISSIONS = 200;

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    if (request.method === "GET" && url.pathname === "/health") {
      return json({ status: "ok" });
    }

    if (request.method !== "POST" || url.pathname !== "/submit") {
      return new Response("Not found", { status: 404 });
    }

    const ip = request.headers.get("cf-connecting-ip") || "unknown";

    const limited = await checkRateLimit(env, ip);
    if (limited) return json({ error: "rate limited" }, 429);

    const lengthHeader = request.headers.get("content-length");
    if (lengthHeader && Number(lengthHeader) > MAX_BODY_BYTES) {
      return json({ error: "payload too large" }, 413);
    }

    let body;
    try {
      body = await request.json();
    } catch {
      return json({ error: "invalid json" }, 400);
    }

    const subs = Array.isArray(body?.submissions) ? body.submissions : null;
    if (!subs || subs.length === 0 || subs.length > MAX_SUBMISSIONS) {
      return json({ error: "invalid submissions" }, 400);
    }

    const valid = subs.every(
      (s) =>
        typeof s?.bundleId === "string" &&
        typeof s?.name === "string" &&
        typeof s?.observedVersion === "string",
    );
    if (!valid) return json({ error: "malformed submission" }, 400);

    const issue = await createIssue(env, body, subs, ip);
    if (!issue.ok) {
      console.error("github upstream error", issue.status, issue.text);
      return json({ error: "upstream failure" }, 502);
    }

    return json({ accepted: subs.length, issue: issue.number }, 201);
  },
};

async function checkRateLimit(env, ip) {
  if (!env.RATE_LIMIT) return false; // No KV bound (e.g. dev): skip.
  const key = `rl:${ip}`;
  const now = Date.now();
  const raw = await env.RATE_LIMIT.get(key);
  const events = (raw ? JSON.parse(raw) : []).filter((t) => now - t < RATE_WINDOW_MS);
  if (events.length >= RATE_MAX) return true;
  events.push(now);
  await env.RATE_LIMIT.put(key, JSON.stringify(events), {
    expirationTtl: 300,
  });
  return false;
}

async function createIssue(env, body, subs, ip) {
  const today = new Date().toISOString().slice(0, 10);
  const title = `Submission: ${subs.length} plugin${subs.length > 1 ? "s" : ""} (${today})`;

  const lines = subs.map((s) => {
    const parts = [
      `- **${escapeMd(s.name)}** \`${escapeMd(s.bundleId)}\``,
      `  - observed: \`${escapeMd(s.observedVersion)}\``,
    ];
    if (s.vendor) parts.push(`  - vendor: ${escapeMd(s.vendor)}`);
    if (s.vendorPage) parts.push(`  - vendor page: ${s.vendorPage}`);
    if (s.downloadURL) parts.push(`  - download: ${s.downloadURL}`);
    if (s.notes) parts.push(`  - notes: ${escapeMd(s.notes)}`);
    return parts.join("\n");
  });

  const issueBody = [
    `client: \`${escapeMd(body.clientVersion || "unknown")}\``,
    `submitted: ${new Date().toISOString()}`,
    `ip-hash: ${await hashIp(ip)}`,
    "",
    "## Plugins",
    "",
    ...lines,
  ].join("\n");

  const resp = await fetch(`https://api.github.com/repos/${env.GITHUB_REPO}/issues`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.GITHUB_TOKEN}`,
      Accept: "application/vnd.github+json",
      "User-Agent": "plupdate-submit-worker",
      "X-GitHub-Api-Version": "2022-11-28",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      title,
      body: issueBody,
      labels: ["submission"],
    }),
  });

  if (!resp.ok) {
    return { ok: false, status: resp.status, text: await resp.text() };
  }
  const data = await resp.json();
  return { ok: true, number: data.number };
}

async function hashIp(ip) {
  // Short, irreversible identifier for spam-pattern correlation in the issue.
  // Don't store IPs raw.
  const bytes = new TextEncoder().encode(`plupdate:${ip}`);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest).slice(0, 6))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

function escapeMd(s) {
  return String(s).replace(/[\\`*_{}\[\]<>]/g, (c) => `\\${c}`);
}

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}
