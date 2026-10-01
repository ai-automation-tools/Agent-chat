<h1 align="center">🎨 Avatar Prompts</h1>

<p align="center">
  <em>Image-generation prompts for persona avatars — one file per persona group,
  one prompt per card, all in the house comic-book style.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/groups-1-2ea44f?style=for-the-badge" alt="1 group">
  <img src="https://img.shields.io/badge/prompts-11-F97316?style=for-the-badge" alt="11 prompts">
</p>

---

## 🗂️ Files

| File | Group | Prompts |
|:---|:---|:---|
| [`podcast-personalities.md`](podcast-personalities.md) | Podcast Personalities | 11 |

## 🛠️ How to use these

1. Prepend the **style prefix** to a persona prompt and generate a **square (1:1)**
   image in any image model: Gemini / nanobanana, ChatGPT, Canva, FLUX.
2. Crop to square and resize to **512×512 PNG**, the size of the existing art.
3. Attach it to the persona. Two options:
   - **Upload to the DB row** (recommended): the `/personas` page, or
     `orchestrator.personas.set_avatar(slug, base64_png, group=...)`. Syncs to the
     hosted mirror with no deploy.
   - **Ship a file** as `images/AgentChat-Avatars/<slug>-avatar.png`. Needs a
     commit and a Fly deploy, since the folder is copied into the image.

> [!NOTE]
> Uploads are raster-only (PNG/JPEG/WebP/GIF, typed by magic bytes). SVG is refused.
> An uploaded image wins over a shipped file; see `docs/App/web-ui.md` for the
> resolution order.

<p align="center">
  <sub><a href="../README.md">Prompts</a> · <a href="../../README.md">Agent-Chat</a></sub>
</p>
