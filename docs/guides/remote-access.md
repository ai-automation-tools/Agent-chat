<h1 align="center">🌐 Reach it from your phone <sub>(optional)</sub></h1>

<p align="center">
  <em>Open your own local Roundtable from a phone, a laptop, or anywhere else —<br>
  over a private Tailscale network, with nothing on the public internet.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Where-tailscale_serve-10b981?style=for-the-badge&labelColor=09090b" alt="tailscale serve">
  <img src="https://img.shields.io/badge/Code_changes-0-0284c7?style=for-the-badge&labelColor=09090b" alt="No code changes">
  <img src="https://img.shields.io/badge/Public_exposure-none-8b5cf6?style=for-the-badge&labelColor=09090b" alt="No public exposure">
</p>

---

Roundtable is local-first: the web UI binds `127.0.0.1:8765` and has no login.
This guide does **not** change that. It puts the loopback port on your own
[Tailscale](https://tailscale.com) network, so every device signed into your
tailnet can open it and nothing else can. One command, nothing to rebuild, no
config file to edit.

> [!IMPORTANT]
> **The network is the login.** Whoever reaches this page can do everything the
> local UI can: stop or delete conversations, edit personas, change Settings,
> and **launch a run** — which spawns CLI agent windows on your PC. On a
> personal tailnet that is you and your devices, which is the point. Never put
> `:8765` on a public interface, a LAN you don't control, or a `tailscale funnel`.

## What you get

```
   your phone / laptop                   your PC (everything stays here)
   ┌──────────────┐                      ┌──────────────────────────────────┐
   │   browser    │ ── WireGuard ──────► │ tailscale serve  :8765 (tailnet) │
   └──────────────┘    tailnet only      │        │ loopback                │
                                         │        ▼                         │
                                         │ web_ui.py  127.0.0.1:8765        │
                                         │ db/chat.db · CLI agents · MCP    │
                                         └──────────────────────────────────┘
```

- Watch a live debate stream in from the couch, stop it, read the archive.
- Kick off a run from the `/orchestrate` form — the CLI windows open on the PC.
- Review AgentBattleground drafts on the `/battleground` console. Approving
  there still **does not** insert into a page; that needs the extension tab on
  the PC.

Everything the page does is same-origin — relative `fetch` and `EventSource`
calls — so the one URL works wherever it is served from. No CORS, no proxy, no
build step.

## Prerequisites

- The web UI running and answering at `http://127.0.0.1:8765/` on your PC
  ([quick start](../../README.md#-quick-start)).
- Admin rights on the PC to install Tailscale.
- A free Tailscale account, signed in on the PC and on each device you want to
  use.

## Setup

**1. Install Tailscale** on the PC and on your phone, and sign in to the same
account on both.

```powershell
winget install Tailscale.Tailscale
```

**2. Publish the port on your tailnet.**

```powershell
tailscale serve --bg --http=8765 http://127.0.0.1:8765
```

It prints the URL. `tailscale serve status` shows it again any time:

```
http://my-pc.tailnet-name.ts.net:8765 (tailnet only)
|-- / proxy http://127.0.0.1:8765
```

`tailscaled` reaches the web UI over loopback and re-serves it **on the tailnet
only**. Nothing binds a public interface, and the config persists across
reboots. `--http=` is deliberate — see the box below.

**3. Turn off key expiry on the PC.** [Admin → Machines](https://login.tailscale.com/admin/machines)
→ your PC → **Disable key expiry**.

> [!WARNING]
> **This is the step that bites months later.** Node keys expire after 180 days
> by default. When the PC's does, the URL still resolves and simply stops
> answering — no warning, no obvious link to anything you changed. Disable it
> for the machine in the server role. Leaving it on for the phone is fine: a
> phone that needs re-auth tells you; a PC that drops off silently does not.

**4. Open it on your phone**: `http://my-pc.tailnet-name.ts.net:8765`. Add it to
the home screen. Done.

> [!IMPORTANT]
> **Use `--http=`, not the short form.** `tailscale serve --bg 8765` implies TLS.
> If HTTPS certificates are not enabled for your tailnet, it **hangs forever**
> trying to provision one instead of failing with a message — you have to kill
> it. `tailscale status --json` reporting `"CertDomains": null` means HTTPS is
> off.
>
> Plain HTTP here is not the hole it looks like: every byte on a tailnet is
> WireGuard-encrypted device to device. The browser just can't see that, so it
> says "Not secure".

> [!NOTE]
> **`serve`, not `funnel`.** They look interchangeable and are opposites.
> `serve` publishes to your tailnet; `funnel` publishes to the **public
> internet** — a page with no login that can spawn processes on your PC, on a
> URL anyone can open. Don't.

## Optional: a password as a second factor

Tailnet membership is the gate. If you want a password *behind* it as well —
say, other people share your tailnet — the web UI already ships HTTP basic auth,
off by default:

```powershell
setx AGENT_CHAT_BASIC_AUTH_PASSWORD "a-long-random-string"
setx AGENT_CHAT_BASIC_AUTH_USER "mike"        # optional; defaults to admin
```

Then restart the web UI. `setx` writes to your **user** environment, which is
where the logon task that autostarts the app reads from; an `$env:` assignment
in one terminal would not reach it. Two things to know:

- It gates **every** address the process answers on, including `127.0.0.1` in
  your own browser. One process, one middleware.
- `/api/ingest` and `/api/since` are exempt — they carry their own bearer token
  for the sync sidecar.

Details in [web-ui.md → Auth](../app/web-ui.md#auth).

## Optional: HTTPS

Worth it if the "Not secure" badge bothers you, or you want a PWA-style home
screen app (service workers need a secure context).

1. Enable **HTTPS Certificates** under [Admin → DNS](https://login.tailscale.com/admin/dns).
2. Re-publish on an HTTPS port, keeping the number so nothing else moves:

   ```powershell
   tailscale serve --http=8765 off
   tailscale serve --bg --https=8765 http://127.0.0.1:8765
   ```

   The URL becomes `https://my-pc.tailnet-name.ts.net:8765`.

The trade-off: issuing a certificate publishes your machine name to public
**Certificate Transparency** logs. The name becomes *knowable*, not reachable.
That's why it is a step here and not the default.

## Keeping it up

- **The serve config persists** in `tailscaled` state across reboots. Nothing
  to re-run.
- **The web UI's keeper is the one you already have.** If you registered the
  scheduled tasks
  ([`scripts/setup/register-app-tasks.ps1`](../../scripts/setup/register-app-tasks.ps1)),
  [`healthcheck-app.ps1`](../../scripts/healthcheck-app.ps1) probes
  `127.0.0.1:8765` on a timer and restarts a dead web UI. Tailscale forwards to
  whatever is listening, so a restarted UI is back on the phone without any
  Tailscale step.
- **More than one app on the same PC** is fine — each gets its own port.
  `tailscale serve status` lists them all.

**To turn it off:**

```powershell
tailscale serve --http=8765 off
```

## Troubleshooting

| Symptom | Likely cause / fix |
|:---|:---|
| Works on the PC, not on the phone | Run `tailscale status` on the PC and read the phone's row. `offline` means the phone's Tailscale client has gone to sleep (Android suspends it after an update, reboot, or battery optimisation). Opening the Tailscale app once wakes it. A `curl` on the PC proves nothing — the PC is always on the tailnet. |
| Nothing resolves on the phone | Both devices signed into the **same** tailnet? MagicDNS on in the admin console? Type the full `http://…:8765` — Chrome's HTTPS-first mode drops the scheme you didn't type. |
| **404 page not found**, plain text | That is `tailscale serve` itself: no handler matched the **Host** header. It is what you get when you open the tailnet **IP** instead of the name. Use the MagicDNS name. |
| **502**, empty body | `serve` is fine; its upstream is down. `curl http://127.0.0.1:8765/` on the PC. If nothing answers, `.\scripts\startup-app.ps1` (or wait for the health check). |
| `tailscale serve --bg 8765` hangs, no output | It's trying to provision a TLS cert on a tailnet without HTTPS. Kill it, use `--http=8765`, or enable certificates first. |
| Worked for months, then stopped, nothing changed | Node key expiry — the 180-day default. `Self.KeyExpiry` in `tailscale status --json`. Re-authenticate, then disable expiry for the PC. |
| The URL changed by itself | The device name follows the Windows hostname; renaming the PC renames the URL. Pin the machine name in the admin console. Enabling HTTPS also changes the scheme. |
| Live messages don't stream on the phone | They go over the same `/api/…/stream` SSE call the PC uses, so if the page loads, the stream works. If it doesn't, the phone's browser has backgrounded the tab — SSE reconnects on its own when you return. |
| Browser asks for a password you never set | `AGENT_CHAT_BASIC_AUTH_PASSWORD` is set in the user environment. `[Environment]::GetEnvironmentVariable('AGENT_CHAT_BASIC_AUTH_PASSWORD','User')` shows it. |

## Security checklist

- [ ] Roundtable is reachable **only** over `tailscale serve` — never a raw
      port on a LAN or the internet, never `tailscale funnel`.
- [ ] The web UI still binds `127.0.0.1`. You did not pass `--host 0.0.0.0`
      "to make it work" — `serve` is what makes it work.
- [ ] Key expiry is disabled on the PC, and you know that a lost phone stays on
      the tailnet until you remove it at
      [Admin → Machines](https://login.tailscale.com/admin/machines).
- [ ] If anyone else is on your tailnet, basic auth is on.
- [ ] You understand that the `/orchestrate` form **spawns CLI windows on the
      PC**, from any device that can open the page.

## 🔗 Related

| Doc | Why |
|:---|:---|
| [`../app/web-ui.md`](../app/web-ui.md) | The routes you are reaching, the SSE channel, the basic-auth and read-only posture. |
| [`orchestrate-form.md`](orchestrate-form.md) | The form that now works from your phone — and what it launches on the PC. |
| [`battleground.md`](battleground.md) | Why approving a draft on the `/battleground` console remotely still needs the extension tab to post. |
| [`../../scripts/README.md`](../../scripts/README.md) | `startup-app.ps1` and `healthcheck-app.ps1`, the keepers for the upstream. |

---

<p align="center">
  <sub>← <a href="README.md">Guides</a> · <a href="../../README.md">Roundtable</a> · Next: <a href="orchestrate-form.md">The orchestrate form →</a></sub>
</p>
