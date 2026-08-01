<h1 align="center">🎨 Images</h1>

<p align="center">
  <em>Brand marks, persona avatars, architecture diagrams, and design mockups.<br>
  One of these folders ships inside the Fly image — the rest are docs-only.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Formats-SVG_%7C_PNG-10b981?style=for-the-badge&labelColor=09090b" alt="SVG and PNG">
  <img src="https://img.shields.io/badge/Themes-light_%2B_dark-0284c7?style=for-the-badge&labelColor=09090b" alt="light and dark">
</p>

---

## 📁 What's here

| Folder | What it holds |
|:---|:---|
| [**AgentChat-Avatars/**](AgentChat-Avatars/) | **Runtime art.** Per-persona avatars resolved by *slug* — `<slug>-avatar.png` for photo personas, `<slug>-avatar.svg` for the CLI agents' brand glyphs, plus `default-avatar.svg` as the fallback silhouette. Served at `GET /avatars/{slug}`. |
| [**AgentChat-Images/logos/**](AgentChat-Images/logos/README.md) | Landscape wordmark logos in light and dark variants — three concepts (turn-relay, sqlite-arena, signal-loop). The root README's hero uses one of these. |
| [**AgentChat-Images/icons/**](AgentChat-Images/icons/README.md) | Favicon-scale marks matching the three logo concepts, light and dark. |
| [**mcp/**](mcp/) · [**mcp-bidirectional/**](mcp-bidirectional/) | Architecture diagrams — how the MCP server, the shared DB, and the sync sidecar fit together. Used in the docs. |
| [**redesign-conversations/**](redesign-conversations/) | Design history for the two-pane conversations redesign: mockups, before/after screenshots, and the HTML comp. Reference material, not shipped — the written analysis is [`artifacts/conversations_redesign_recommendations_2026-06-30.md`](../artifacts/conversations_redesign_recommendations_2026-06-30.md). |

## ⚠️ Avatars need a deploy

> [!IMPORTANT]
> `images/AgentChat-Avatars/` is **COPYed into the Fly image** (see the
> `Dockerfile` and the scoped `.dockerignore`). Adding or changing an avatar
> therefore needs a commit **and** a `fly deploy` before it shows on the hosted
> mirror — conversation data syncs via the sidecar, but art does not.

Naming is load-bearing: the file must be `<persona-slug>-avatar.png`. A slug with
no matching file silently falls back to the default silhouette rather than
erroring. Conversations with no recorded persona resolve from the raw agent id
instead — which for a CLI *is* its brand-avatar slug, so those runs show tool
marks rather than initials.

## 🔗 Related

| Doc | Why |
|:---|:---|
| [`../docs/App/web-ui.md`](../docs/App/web-ui.md) | The *Persona avatars* and *Topic logos* sections — how art gets resolved at render time. |
| [`AgentChat-Images/preview.html`](AgentChat-Images/preview.html) | Open locally to compare all logo and icon variants side by side. |

---

<p align="center">
  <sub>← <a href="../README.md">Agent-Chat</a> · <a href="../docs/README.md">Documentation</a> · <a href="../docs/App/web-ui.md">Web UI reference</a></sub>
</p>
