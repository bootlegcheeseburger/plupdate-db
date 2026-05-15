// Plupdate submission relay + admin promote layer.
//
// Routes:
//   GET  /health        -> 200 ok
//   POST /submit        -> dedupe by bundleId; +1 comment on open issue, else new
//   GET  /admin         -> token-gated HTML page listing open submissions
//   GET  /admin/issues  -> token-gated JSON list of open submissions
//   POST /promote       -> token-gated; scaffold a PR on the DB repo from a submission
//
// Secrets (set via `wrangler secret put`):
//   GITHUB_TOKEN   - fine-grained PAT, Issues:write on the submissions repo
//   PROMOTE_TOKEN  - fine-grained PAT, Contents+PullRequests:write on the DB repo
//   ADMIN_TOKEN    - long random string; required for /admin and /promote
//
// Vars (in wrangler.toml, public):
//   GITHUB_REPO    - "owner/plupdate-submissions"
//   PROMOTE_REPO   - "owner/plupdate-db"
//
// Bindings (in wrangler.toml):
//   RATE_LIMIT     - Workers KV namespace for IP rate-limit state

const RATE_WINDOW_MS = 60_000;
const RATE_MAX = 10;
const MAX_BODY_BYTES = 64 * 1024;
const MAX_SUBMISSIONS = 200;

// Hidden HTML comment we embed in every issue body so dedupe lookups are
// title-rename-proof.
const BUNDLE_ID_MARKER = (id) => `<!-- bundleId: ${id} -->`;
const BUNDLE_ID_MARKER_RE = /<!-- bundleId: ([^ ]+) -->/;

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const { pathname } = url;

    if (request.method === "GET" && pathname === "/health") {
      return json({ status: "ok" });
    }

    if (request.method === "POST" && pathname === "/submit") {
      return handleSubmit(request, env);
    }

    if (request.method === "GET" && pathname === "/admin") {
      if (!checkAdminTokenQuery(url, env)) return unauthorized();
      return new Response(ADMIN_HTML, {
        headers: { "content-type": "text/html; charset=utf-8" },
      });
    }

    if (request.method === "GET" && pathname === "/admin/issues") {
      if (!checkAdminTokenQuery(url, env)) return unauthorized();
      return handleAdminIssues(env);
    }

    if (request.method === "POST" && pathname === "/promote") {
      if (!checkAdminTokenHeader(request, env)) return unauthorized();
      return handlePromote(request, env);
    }

    return new Response("Not found", { status: 404 });
  },
};

// --- /submit ---------------------------------------------------------------

async function handleSubmit(request, env) {
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

  const results = await processSubmissions(env, body, subs, ip);
  const failed = results.filter((r) => !r.ok);
  if (failed.length === results.length) {
    console.error("all submissions failed", failed);
    return json({ error: "upstream failure" }, 502);
  }

  return json(
    { accepted: results.length - failed.length, results },
    failed.length ? 207 : 201,
  );
}

async function processSubmissions(env, body, subs, ip) {
  // Group by bundleId so we make at most one decision per unique plugin
  // even if the same id appears multiple times in one POST.
  const byBundleId = new Map();
  for (const s of subs) {
    if (!byBundleId.has(s.bundleId)) byBundleId.set(s.bundleId, []);
    byBundleId.get(s.bundleId).push(s);
  }

  const openIssues = await listOpenSubmissionIssues(env);
  const ipHash = await hashIp(ip);
  const clientVersion = body?.clientVersion || "unknown";

  const results = [];
  for (const [bundleId, occurrences] of byBundleId) {
    const existing = openIssues.find(
      (i) => extractBundleId(i.body) === bundleId,
    );
    if (existing) {
      const r = await commentOnIssue(
        env,
        existing.number,
        occurrences[0],
        ipHash,
      );
      results.push({
        bundleId,
        action: "comment",
        issue: existing.number,
        ok: r.ok,
        ...(r.ok ? {} : { status: r.status }),
      });
    } else {
      const r = await openNewIssue(env, occurrences[0], ipHash, clientVersion);
      results.push({
        bundleId,
        action: "open",
        issue: r.number ?? null,
        ok: r.ok,
        ...(r.ok ? {} : { status: r.status }),
      });
    }
  }
  return results;
}

async function listOpenSubmissionIssues(env) {
  // First 100 open submission issues. Past that we'd paginate; punt until
  // the inbox actually crosses that line.
  const resp = await ghFetch(env, "GITHUB_TOKEN", env.GITHUB_REPO, "GET", "/issues", {
    query: { state: "open", labels: "submission", per_page: "100" },
  });
  if (!resp.ok) {
    console.error("list issues failed", resp.status, await resp.text());
    return [];
  }
  const all = await resp.json();
  // GitHub returns PRs in the issues list too; filter them out.
  return all.filter((i) => !i.pull_request);
}

async function commentOnIssue(env, number, submission, ipHash) {
  const body = [
    `+1 from \`${ipHash}\``,
    `observed: \`${escapeMd(submission.observedVersion)}\``,
    `submitted: ${new Date().toISOString()}`,
  ].join("\n");

  const resp = await ghFetch(
    env,
    "GITHUB_TOKEN",
    env.GITHUB_REPO,
    "POST",
    `/issues/${number}/comments`,
    { json: { body } },
  );
  if (!resp.ok) {
    return { ok: false, status: resp.status };
  }
  return { ok: true };
}

async function openNewIssue(env, submission, ipHash, clientVersion) {
  const title = `New plugin: ${submission.bundleId}`;

  const lines = [
    BUNDLE_ID_MARKER(submission.bundleId),
    "",
    `**${escapeMd(submission.name)}**`,
    `- bundle id: \`${escapeMd(submission.bundleId)}\``,
    `- observed version: \`${escapeMd(submission.observedVersion)}\``,
  ];
  if (submission.vendor) lines.push(`- vendor: ${escapeMd(submission.vendor)}`);
  if (submission.vendorPage) lines.push(`- vendor page: ${submission.vendorPage}`);
  if (submission.downloadURL) lines.push(`- download: ${submission.downloadURL}`);
  if (submission.notes) lines.push(`- notes: ${escapeMd(submission.notes)}`);
  lines.push(
    "",
    `---`,
    `client: \`${escapeMd(clientVersion)}\``,
    `submitted: ${new Date().toISOString()}`,
    `ip-hash: \`${ipHash}\``,
  );

  const resp = await ghFetch(env, "GITHUB_TOKEN", env.GITHUB_REPO, "POST", "/issues", {
    json: { title, body: lines.join("\n"), labels: ["submission"] },
  });
  if (!resp.ok) {
    return { ok: false, status: resp.status };
  }
  const data = await resp.json();
  return { ok: true, number: data.number };
}

function extractBundleId(issueBody) {
  if (!issueBody) return null;
  const m = issueBody.match(BUNDLE_ID_MARKER_RE);
  return m ? m[1] : null;
}

// --- /admin ----------------------------------------------------------------

async function handleAdminIssues(env) {
  const issues = await listOpenSubmissionIssues(env);
  const parsed = issues.map((i) => ({
    issueNumber: i.number,
    title: i.title,
    bundleId: extractBundleId(i.body),
    body: i.body,
    htmlUrl: i.html_url,
    createdAt: i.created_at,
  }));
  return json({ issues: parsed });
}

// --- /promote --------------------------------------------------------------

async function handlePromote(request, env) {
  if (!env.PROMOTE_TOKEN || !env.PROMOTE_REPO) {
    return json({ error: "promote not configured" }, 500);
  }
  let body;
  try {
    body = await request.json();
  } catch {
    return json({ error: "invalid json" }, 400);
  }
  const { bundleId, vendorSlug, name } = body || {};
  if (
    typeof bundleId !== "string" ||
    typeof vendorSlug !== "string" ||
    typeof name !== "string"
  ) {
    return json({ error: "missing required fields" }, 400);
  }
  if (!/^[a-z0-9-]+$/.test(vendorSlug) || vendorSlug.startsWith("_")) {
    return json({ error: "invalid vendor slug" }, 400);
  }

  try {
    const result = await scaffoldPromotionPR(env, body);
    return json(result, 201);
  } catch (e) {
    console.error("promote failed", e?.message || e);
    return json({ error: String(e?.message || e) }, 500);
  }
}

async function scaffoldPromotionPR(env, input) {
  const {
    bundleId,
    vendorSlug,
    name,
    observedVersion,
    vendor,
    vendorPage,
    downloadURL,
    notes,
    issueNumber,
  } = input;

  const vendorPath = `db/vendors/${vendorSlug}.json`;
  const indexPath = `db/vendors/index.json`;

  // Read vendor file and index in parallel.
  const [vendorFile, indexFile] = await Promise.all([
    readFileFromRepo(env, vendorPath),
    readFileFromRepo(env, indexPath),
  ]);

  if (!indexFile) {
    throw new Error("vendors/index.json missing from db repo");
  }

  let vendorJson;
  let isNewVendor = false;
  if (vendorFile) {
    vendorJson = JSON.parse(vendorFile.content);
    if (
      Array.isArray(vendorJson.plugins) &&
      vendorJson.plugins.some((p) => p.bundleId === bundleId)
    ) {
      throw new Error(
        `bundleId ${bundleId} already in vendors/${vendorSlug}.json`,
      );
    }
  } else {
    isNewVendor = true;
    vendorJson = {
      vendor: vendor || vendorSlug,
      homepage: null,
      plugins: [],
    };
  }

  vendorJson.plugins.push({
    bundleId,
    name,
    latestVersion: observedVersion || "TODO",
    vendorPage: vendorPage || null,
    downloadURL: downloadURL || null,
    notes: notes || null,
  });
  vendorJson.plugins.sort((a, b) => a.name.localeCompare(b.name));

  const newVendorText = JSON.stringify(vendorJson, null, 2) + "\n";

  let newIndexText = null;
  let indexSha = indexFile.sha;
  if (isNewVendor) {
    const indexJson = JSON.parse(indexFile.content);
    if (!Array.isArray(indexJson.vendors)) {
      throw new Error("vendors/index.json has unexpected shape");
    }
    if (!indexJson.vendors.includes(vendorSlug)) {
      indexJson.vendors.push(vendorSlug);
      indexJson.vendors.sort();
      indexJson.updatedAt = new Date().toISOString().replace(/\.\d+/, "");
      newIndexText = JSON.stringify(indexJson, null, 2) + "\n";
    }
  }

  const branch = `promote/${safeBranchName(bundleId)}-${Date.now().toString(36)}`;
  await createBranch(env, branch);
  await writeFileToBranch(
    env,
    branch,
    vendorPath,
    newVendorText,
    vendorFile?.sha,
    `Add ${bundleId} to ${vendorSlug}.json`,
  );
  if (newIndexText) {
    await writeFileToBranch(
      env,
      branch,
      indexPath,
      newIndexText,
      indexSha,
      `Add ${vendorSlug} to index`,
    );
  }

  const prTitle = `promote: ${bundleId}`;
  const prBody = [
    `Scaffolded from a user submission. Maintainer should review and fill in any missing fields (homepage, vendorPage, latestVersion, drm) before merging.`,
    "",
    `- vendor file: \`${vendorPath}\``,
    `- new vendor: \`${isNewVendor}\``,
    issueNumber
      ? `\nCloses ${env.GITHUB_REPO}#${issueNumber} upon merge.`
      : "",
  ]
    .filter(Boolean)
    .join("\n");

  const pr = await createPR(env, branch, prTitle, prBody);

  if (issueNumber) {
    await commentOnSubmissionIssue(
      env,
      issueNumber,
      `Promotion PR opened: ${pr.html_url}`,
    );
  }

  return {
    pr: pr.html_url,
    prNumber: pr.number,
    branch,
    isNewVendor,
  };
}

async function readFileFromRepo(env, path) {
  const resp = await ghFetch(
    env,
    "PROMOTE_TOKEN",
    env.PROMOTE_REPO,
    "GET",
    `/contents/${path}`,
    { query: { ref: "main" } },
  );
  if (resp.status === 404) return null;
  if (!resp.ok) {
    throw new Error(`read ${path} failed: ${resp.status}`);
  }
  const data = await resp.json();
  return {
    sha: data.sha,
    content: b64decodeUtf8(data.content),
  };
}

async function createBranch(env, branch) {
  // Get main's tip SHA, then create ref.
  const mainResp = await ghFetch(
    env,
    "PROMOTE_TOKEN",
    env.PROMOTE_REPO,
    "GET",
    `/git/ref/heads/main`,
  );
  if (!mainResp.ok) {
    throw new Error(`get main ref failed: ${mainResp.status}`);
  }
  const main = await mainResp.json();
  const refResp = await ghFetch(
    env,
    "PROMOTE_TOKEN",
    env.PROMOTE_REPO,
    "POST",
    `/git/refs`,
    {
      json: { ref: `refs/heads/${branch}`, sha: main.object.sha },
    },
  );
  if (!refResp.ok) {
    throw new Error(`create branch failed: ${refResp.status}`);
  }
}

async function writeFileToBranch(env, branch, path, text, sha, message) {
  const body = {
    message,
    content: b64encodeUtf8(text),
    branch,
  };
  if (sha) body.sha = sha;
  const resp = await ghFetch(
    env,
    "PROMOTE_TOKEN",
    env.PROMOTE_REPO,
    "PUT",
    `/contents/${path}`,
    { json: body },
  );
  if (!resp.ok) {
    const t = await resp.text();
    throw new Error(`write ${path} failed: ${resp.status} ${t}`);
  }
}

async function createPR(env, branch, title, body) {
  const resp = await ghFetch(env, "PROMOTE_TOKEN", env.PROMOTE_REPO, "POST", `/pulls`, {
    json: { title, body, head: branch, base: "main" },
  });
  if (!resp.ok) {
    const t = await resp.text();
    throw new Error(`create PR failed: ${resp.status} ${t}`);
  }
  return await resp.json();
}

async function commentOnSubmissionIssue(env, number, body) {
  const resp = await ghFetch(
    env,
    "GITHUB_TOKEN",
    env.GITHUB_REPO,
    "POST",
    `/issues/${number}/comments`,
    { json: { body } },
  );
  if (!resp.ok) {
    console.error("comment failed", resp.status, await resp.text());
  }
}

// --- helpers ---------------------------------------------------------------

async function ghFetch(env, tokenVar, repo, method, path, opts = {}) {
  let url = `https://api.github.com/repos/${repo}${path}`;
  if (opts.query) {
    const params = new URLSearchParams(opts.query);
    url += `?${params.toString()}`;
  }
  return fetch(url, {
    method,
    headers: {
      Authorization: `Bearer ${env[tokenVar]}`,
      Accept: "application/vnd.github+json",
      "User-Agent": "plupdate-submit-worker",
      "X-GitHub-Api-Version": "2022-11-28",
      ...(opts.json ? { "Content-Type": "application/json" } : {}),
    },
    body: opts.json ? JSON.stringify(opts.json) : undefined,
  });
}

async function checkRateLimit(env, ip) {
  if (!env.RATE_LIMIT) return false; // No KV bound (e.g. dev): skip.
  const key = `rl:${ip}`;
  const now = Date.now();
  const raw = await env.RATE_LIMIT.get(key);
  const events = (raw ? JSON.parse(raw) : []).filter(
    (t) => now - t < RATE_WINDOW_MS,
  );
  if (events.length >= RATE_MAX) return true;
  events.push(now);
  await env.RATE_LIMIT.put(key, JSON.stringify(events), {
    expirationTtl: 300,
  });
  return false;
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

function safeBranchName(s) {
  return String(s).toLowerCase().replace(/[^a-z0-9-]+/g, "-").replace(/-+/g, "-");
}

function b64encodeUtf8(str) {
  const bytes = new TextEncoder().encode(str);
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin);
}

function b64decodeUtf8(b64) {
  const bin = atob(b64.replace(/\s/g, ""));
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new TextDecoder().decode(bytes);
}

function checkAdminTokenHeader(request, env) {
  const auth = request.headers.get("Authorization") || "";
  return env.ADMIN_TOKEN && auth === `Bearer ${env.ADMIN_TOKEN}`;
}

function checkAdminTokenQuery(url, env) {
  const t = url.searchParams.get("token");
  return env.ADMIN_TOKEN && t === env.ADMIN_TOKEN;
}

function unauthorized() {
  return json({ error: "unauthorized" }, 401);
}

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

// --- admin page ------------------------------------------------------------

const ADMIN_HTML = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>plupdate admin</title>
<style>
  body { font: 14px/1.4 -apple-system, system-ui, sans-serif; max-width: 900px; margin: 2rem auto; padding: 0 1rem; }
  h1 { font-size: 1.2rem; }
  table { width: 100%; border-collapse: collapse; }
  th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid #eee; vertical-align: top; }
  th { background: #fafafa; font-weight: 600; }
  input[type=text] { width: 100%; padding: 4px 6px; box-sizing: border-box; font: inherit; }
  button { padding: 6px 10px; cursor: pointer; }
  .muted { color: #888; font-size: 12px; }
  .ok { color: green; }
  .err { color: #c33; }
  code { background: #f4f4f4; padding: 1px 4px; border-radius: 3px; }
</style>
</head>
<body>
<h1>plupdate-submissions inbox</h1>
<p class="muted">Pick a slug, hit Promote, and the Worker opens a PR on plupdate-db. Slug defaults to the second segment of the bundle id (e.g. <code>com.foo.Bar</code> -> <code>foo</code>); fix it before promoting if wrong.</p>
<div id="status" class="muted">Loading...</div>
<table id="rows" hidden>
  <thead><tr><th>Issue</th><th>Bundle</th><th>Vendor slug</th><th></th></tr></thead>
  <tbody></tbody>
</table>

<script>
const params = new URLSearchParams(location.search);
const token = params.get("token");
if (!token) { document.getElementById("status").textContent = "Missing ?token="; }

function defaultSlug(bundleId) {
  // Heuristic: com.vendor.Plugin -> "vendor"
  const parts = (bundleId || "").split(".");
  return (parts[1] || "").toLowerCase().replace(/[^a-z0-9-]/g, "");
}

function parseBody(body) {
  // Pull "**Name**" and "observed version: \`X.Y\`" out of the new-issue body.
  const m = (body || "").match(/\\*\\*(.+?)\\*\\*/);
  const v = (body || "").match(/observed version: \\\`(.+?)\\\`/);
  return { name: m ? m[1] : "", observedVersion: v ? v[1] : "" };
}

async function loadIssues() {
  const r = await fetch("/admin/issues?token=" + encodeURIComponent(token));
  if (!r.ok) {
    document.getElementById("status").textContent = "Failed to load: " + r.status;
    return;
  }
  const { issues } = await r.json();
  const tbody = document.querySelector("#rows tbody");
  tbody.innerHTML = "";
  for (const i of issues) {
    if (!i.bundleId) continue;
    const { name, observedVersion } = parseBody(i.body);
    const tr = document.createElement("tr");
    tr.innerHTML = \`
      <td><a href="\${i.htmlUrl}" target="_blank">#\${i.issueNumber}</a><div class="muted">\${i.createdAt.slice(0,10)}</div></td>
      <td><strong>\${escape(name) || "(unknown)"}</strong><div class="muted"><code>\${escape(i.bundleId)}</code><br>v\${escape(observedVersion) || "?"}</div></td>
      <td><input type="text" value="\${escape(defaultSlug(i.bundleId))}" data-field="vendorSlug"></td>
      <td><button>Promote</button><div class="msg muted"></div></td>
    \`;
    const btn = tr.querySelector("button");
    const msg = tr.querySelector(".msg");
    btn.onclick = async () => {
      btn.disabled = true;
      msg.textContent = "Working...";
      msg.className = "msg muted";
      const slug = tr.querySelector("[data-field=vendorSlug]").value.trim();
      const res = await fetch("/promote", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": "Bearer " + token,
        },
        body: JSON.stringify({
          bundleId: i.bundleId,
          vendorSlug: slug,
          name,
          observedVersion,
          issueNumber: i.issueNumber,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok) {
        msg.textContent = "OK: " + (data.pr || "PR opened");
        msg.className = "msg ok";
      } else {
        msg.textContent = "Error: " + (data.error || res.status);
        msg.className = "msg err";
        btn.disabled = false;
      }
    };
    tbody.appendChild(tr);
  }
  document.getElementById("status").textContent = issues.length + " open submission(s)";
  document.getElementById("rows").hidden = false;
}

function escape(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\\"":"&quot;","'":"&#39;"}[c]));
}

if (token) loadIssues();
</script>
</body>
</html>
`;
