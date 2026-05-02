# Hosting Agent-Chat as a Public Site

This doc lays out the realistic options for putting Agent-Chat on the public internet given what this repo actually is, and recommends a path using the assets already on hand: a custom domain, GitHub Pages, and Vercel.

---

## 1. What "host this" really means here

Agent-Chat is **three different things** and they have **different hosting profiles**. Be explicit about which one you want public before picking a platform.

| Component | What it is | Hostable? |
|:---|:---|:---|
| `src/agent_chat_mcp.py` | A **stdio** MCP server. Each CLI launches its own copy. | **No.** Not a network service. Cannot be "hosted" — it's spawned as a subprocess by Claude Code / Codex CLI. |
| `src/web_ui.py` | A Starlette + SSE app reading `chat.db` directly. Binds to `127.0.0.1` by default, no auth. | **Yes, but with caveats.** It's a stateful Python web app; serverless platforms (Vercel functions, GH Pages) are a poor fit without rework. |
| `README.md` + `docs/*` | Project documentation. | **Yes, easily.** Static site → GH Pages or Vercel, either works. |

> [!IMPORTANT]
> The README states plainly: *"No auth — anything that runs the server with `--agent-id X` is X. Fine for two local CLIs you control; **do not expose this over a network without adding auth**."* That warning applies to the web UI too if its DB contains real conversation content. Anything you host publicly with the current code is **read-only public** — there is no permission layer.

---

## 2. The three realistic options

### Option A — Static project site (recommended starting point)

A docs / landing site built from the existing README + `docs/` folder. No server-side code, no DB, no auth surface. Just a public page that explains the project and links to the GitHub repo.

- **Stack:** Astro + Starlight, MkDocs Material, or Docusaurus. All three convert markdown → static site, all three deploy in one click on GH Pages or Vercel.
- **Pros:** Zero attack surface. Free. Custom domain is trivial. Indexable by search engines. Lowest maintenance.
- **Cons:** No live demo — visitors only see screenshots / docs.
- **Best for:** Showcasing the repo, getting a domain pointed at *something* today, while you decide whether option B is worth the effort.

### Option B — Public read-only web UI demo

Deploy `src/web_ui.py` itself, fronted by a public URL, showing a curated demo `chat.db`.

- **Stack constraints:**
  - Starlette is ASGI → needs a Python runtime, not a static host.
  - SQLite WAL assumes a writable, persistent local filesystem. Serverless functions don't have one.
  - The SSE endpoint (`/api/conversations/<id>/stream`) is a long-lived HTTP connection. Most serverless platforms cap function duration at 10–60s, which breaks the stream.
- **Where it actually fits:**
  - **Fly.io / Render / Railway** — small always-on VM or container. Best fit for the current code with **zero changes**. ~$0–7/mo.
  - **Vercel** — works only if you (a) port the app from Starlette to a Vercel-supported framework (Next.js or FastAPI on Vercel's Python runtime), (b) move state out of local SQLite (Vercel Postgres, Turso/libSQL, Neon), and (c) replace SSE with polling or a hosted realtime layer (Vercel's `streamSSE`, Pusher, Ably). That's a real rewrite, not a deploy.
  - **GitHub Pages** — not viable. GH Pages is static-only; it cannot run Python.
- **Auth:** Whatever you pick, put **HTTP basic auth or Cloudflare Access in front**, or strip the DB to a synthetic demo conversation before deploying. The current code has no login.

### Option C — Hybrid: static site on Vercel + live demo subdomain

Put the docs / landing page on `agentchat.yourdomain.com` (Vercel or GH Pages, static), and the live web UI on `demo.agentchat.yourdomain.com` (Fly.io / Render). The marketing surface stays free and fast; the demo runs where it actually fits.

This is what I'd recommend if you want both. Don't try to force the web UI onto Vercel just because Vercel is what you have.

---

## 3. Recommendation

**Do Option A first this week, then decide on B.**

Concretely:

1. **Generate a static site from the existing markdown.** Astro Starlight is the lowest-friction choice and looks production-quality out of the box. The repo already has `README.md`, `docs/INITIAL_SETUP.md`, `docs/CHANGELOG.md`, `docs/Roadmap.md` — those become the site's content with no rewriting.
2. **Deploy on Vercel** (not GH Pages) for this repo, because:
   - Vercel's GitHub integration auto-deploys every push to `main` and gives every PR a preview URL. GH Pages does main-branch deploy only, no PR previews.
   - Vercel's custom-domain UI handles the apex + `www` redirect automatically. GH Pages requires manual A records to its IPs, and apex + `www` is fiddlier.
   - Build minutes and bandwidth are generous on the free tier for a small docs site.
3. **Skip the live web UI demo for now.** Until the auth gap is closed and the SSE/SQLite design is adapted (or moved to Fly.io as-is), a public demo is more risk than payoff.
4. **Revisit Option B in a follow-up.** When you do, deploy as-is to Fly.io rather than rewriting for Vercel.

---

## 4. Step-by-step: Option A on Vercel with your custom domain

Replace `agent-chat` and `yourdomain.com` with your actual values.

### 4.1 Scaffold the static site

From the repo root on the `mike_desktop` branch (or a feature branch):

```powershell
# Use pnpm — it's the convention in the wider workspace
pnpm create astro@latest site -- --template starlight --no-install --no-git
cd site
pnpm install
```

Astro Starlight gets you:
- Sidebar navigation generated from `src/content/docs/`
- Dark mode, search, mobile responsive
- Markdown + MDX support, syntax highlighting via Shiki

### 4.2 Wire the existing markdown

Two viable approaches:

- **Symlink / copy** the repo's `README.md` and `docs/*.md` into `site/src/content/docs/` at build time. Cleanest for keeping a single source of truth. Add a small `prebuild` script that copies and rewrites relative links.
- **Move** docs into `site/src/content/docs/` and delete the originals. Simpler but the README at the repo root is now duplicated; pick one canonical location.

For each markdown file, add Starlight frontmatter:

```markdown
---
title: Initial Setup
description: Step-by-step bootstrap reproduction.
---
```

### 4.3 Deploy to Vercel

1. Push the branch to GitHub.
2. In Vercel: **Add New… → Project → Import** the `Agent-chat` repo.
3. **Root Directory:** `site` (so Vercel builds the Astro project, not the Python repo).
4. **Framework Preset:** Astro (auto-detected).
5. **Build Command:** `pnpm build` (default).
6. **Output Directory:** `dist` (default for Astro).
7. Deploy. You get a `*.vercel.app` URL within ~60s.

### 4.4 Attach the custom domain

In Vercel → **Project → Settings → Domains**:

1. Add both `agentchat.yourdomain.com` and `yourdomain.com` (or whichever apex/subdomain you want as canonical). Vercel will show you exactly which DNS records to create.
2. At your DNS provider, add the records Vercel asked for. Typical pattern:
   - **Subdomain (`agentchat`)** → `CNAME` to `cname.vercel-dns.com`
   - **Apex (`yourdomain.com`)** → `A` record to `76.76.21.21` (or use your provider's CNAME flattening / ALIAS / ANAME if it supports apex CNAMEs).
3. Wait for propagation (usually <5 min, occasionally up to a few hours).
4. Vercel auto-issues a Let's Encrypt cert. Confirm HTTPS works.
5. Set one of the two domains as the **primary** — Vercel will 308-redirect the other to it.

### 4.5 Lock the deploy down

- Branch deploys: enable for `main` only. Disable preview deploys for unrelated branches if you don't want them public.
- Add a `robots.txt` if the site shouldn't be indexed yet.
- Set up the Vercel **deploy notifications** so failed builds reach you.

---

## 5. If you really want GitHub Pages instead

GH Pages is fine if you'd rather not introduce Vercel as a dependency.

1. Build the Astro site in CI (GitHub Actions: `actions/setup-node` → `pnpm install` → `pnpm build`).
2. Publish `site/dist` to the `gh-pages` branch via `peaceiris/actions-gh-pages` or the official `actions/deploy-pages` flow.
3. Repo → **Settings → Pages → Source: GitHub Actions**.
4. **Settings → Pages → Custom domain:** enter `agentchat.yourdomain.com`. GH writes a `CNAME` file to the published branch automatically.
5. DNS at your provider:
   - **Subdomain:** `CNAME` to `<username>.github.io`.
   - **Apex** (if you want it): four `A` records to `185.199.108.153`, `185.199.109.153`, `185.199.110.153`, `185.199.111.153`.
6. Tick **Enforce HTTPS** in Pages settings once the cert provisions.

What you give up vs. Vercel: per-PR preview URLs, instant rollbacks, edge functions if you ever need them, and slightly faster cold deploys.

---

## 6. Future: hosting the web UI for real (Option B sketch)

Notes for when you come back to this — not work to do now.

### 6.1 Minimum viable changes to the code

- **Auth.** Add HTTP basic auth middleware in front of all routes, or front the deploy with Cloudflare Access / Tailscale Funnel. Don't ship the current zero-auth code to the public internet.
- **Read-only mode flag.** A `--read-only` arg that makes the SQLite connection `mode=ro` is cheap insurance.
- **Bind / proxy.** Keep the app on `127.0.0.1` inside the container, terminate TLS at the platform's edge proxy.

### 6.2 Platform shortlist

| Platform | Fit | Notes |
|:---|:---|:---|
| **Fly.io** | Best | Persistent volume for `chat.db`, always-on machine, free tier covers a small demo. SSE works fine. Dockerfile-based deploy. |
| **Render** | Good | Web Service + persistent disk. Slightly more expensive than Fly for the same workload. |
| **Railway** | Good | Simple GitHub deploy, persistent volumes. Pricing is usage-based. |
| **Vercel** | Poor for this app as written | Serverless function timeouts kill SSE, no writable persistent FS for SQLite WAL. Would require rewriting state to Postgres/Turso and replacing SSE with polling or hosted realtime. |
| **GH Pages** | Not possible | Static-only. |

### 6.3 Suggested layout when you do it

```
demo.agentchat.yourdomain.com    →  Fly.io (Starlette web_ui.py + read-only chat.db)
agentchat.yourdomain.com         →  Vercel (static Astro Starlight docs)
github.com/michaelschecht/Agent-chat  →  source of truth, both deploys auto-trigger
```

---

## 7. Decisions you still need to make

Before doing any of the above, lock these in:

1. **Domain shape.** Is the project living at the apex (`agentchat.com`), a subdomain of a personal domain (`agentchat.michaelschecht.dev`), or a path on an existing site? This drives the DNS section of §4.4.
2. **Repo branch for the site.** Build from `mike_desktop` (current default working branch) or merge into `main` first? Vercel and GH Pages both default to `main` for production builds.
3. **Single source of truth for docs.** Keep `README.md` at repo root and copy into the site at build time, or move docs entirely into the site? Recommend copy-at-build.
4. **Live demo: yes/no.** If yes, the answer is Fly.io, not Vercel, and there's a real engineering task involved (auth + demo DB curation).

Once those are settled the §4 checklist runs in roughly an hour.
