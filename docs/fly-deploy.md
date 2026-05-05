# Deploying the Web UI to Fly.io

Step-by-step procedure for getting `src/web_ui.py` running publicly at
`https://agent-chat.mikesailab.com`. Pairs with `docs/HOSTING.md`, which
explains *why* Fly was picked over Vercel/GH Pages for this app.

---

## What's already in the repo

- `Dockerfile` — multi-stage Python 3.13 slim build. Copies `requirements.txt`
  and `src/`, runs `python src/web_ui.py` on port 8080.
- `fly.toml` — app `agent-chat-mikesailab`, region `iad`, 256 MB shared-cpu-1x
  VM, 1 GB persistent volume mounted at `/data`, auto-stop when idle.
- `.dockerignore` — default-deny so the build context is just
  `requirements.txt + src/`. Anything else (`db/`, `docs/`, `site/`,
  `agents/`, `.venv/`, `.git/`, etc.) stays out.
- `src/web_ui.py` changes:
  - **Auto-init**: `db_init()` runs `CREATE TABLE IF NOT EXISTS` on every boot.
    First request on an empty Fly volume no longer 500s.
  - **Env-var fallbacks**: `--db-path`, `--host`, `--port` default to
    `$AGENT_CHAT_DB`, `$HOST`, `$PORT`. Local dev unchanged — args still win.
  - **HTTP Basic Auth** middleware. Off when
    `AGENT_CHAT_BASIC_AUTH_PASSWORD` is unset (preserves local dev). On when
    set; user defaults to `admin`, override via `AGENT_CHAT_BASIC_AUTH_USER`.

## What you need to run yourself

The rest of this doc is steps you have to execute. None of it can be done
from inside the repo without your Fly account credentials.

### 1. Install flyctl

```powershell
iwr https://fly.io/install.ps1 -useb | iex
# Restart pwsh after install so $env:Path picks it up
fly version
```

> [!NOTE]
> macOS/Linux: `curl -L https://fly.io/install.sh | sh`.

### 2. Auth and create the app

```powershell
fly auth login          # opens a browser
fly apps create agent-chat-mikesailab
```

If `agent-chat-mikesailab` is taken globally, pick another name and update
`app = "..."` in `fly.toml` to match before deploying.

### 3. Create the persistent volume

```powershell
fly volumes create agent_chat_data --region iad --size 1 --app agent-chat-mikesailab
```

1 GB is the minimum and orders of magnitude more than this DB will use.
The volume name must match `[mounts] source` in `fly.toml`.

### 4. Set the basic-auth password as a secret

```powershell
# Pick your own password. This goes into Fly's encrypted secrets store, not the image.
fly secrets set AGENT_CHAT_BASIC_AUTH_PASSWORD='your-strong-password-here' --app agent-chat-mikesailab
# Optional: change the username (defaults to "admin")
# fly secrets set AGENT_CHAT_BASIC_AUTH_USER='mike' --app agent-chat-mikesailab
```

### 5. Deploy

```powershell
fly deploy --app agent-chat-mikesailab
```

First deploy uploads the build context (~few hundred KB thanks to
`.dockerignore`) to Fly's remote builder, builds the image, runs
`fly machines run` to start a single machine on the volume. Takes 1-3 min.

When deploy completes, hit the temporary `*.fly.dev` URL it prints. You
should see the basic-auth challenge, log in, then the empty-conversations
"Seed one with start_conversation.py" page.

### 6. Attach the custom domain

```powershell
fly certs add agent-chat.mikesailab.com --app agent-chat-mikesailab
fly certs show agent-chat.mikesailab.com --app agent-chat-mikesailab
```

`fly certs show` prints the DNS records you need to add. Typical pattern
for a subdomain:

- `CNAME agent-chat → agent-chat-mikesailab.fly.dev` at the
  `mikesailab.com` DNS provider
- An `_acme-challenge.agent-chat` `CNAME` for the cert validation

Once DNS propagates, Fly auto-issues a Let's Encrypt cert. `fly certs show`
flips to `Verified`. Then `https://agent-chat.mikesailab.com` works.

### 7. (Optional) Smoke-test the deploy

```powershell
# Should challenge for credentials
curl.exe -i https://agent-chat.mikesailab.com/

# Should return 200 with creds
curl.exe -i -u admin:your-strong-password-here https://agent-chat.mikesailab.com/api/conversations
# expected body: []
```

---

## Updating the site later

```powershell
# Code changes
fly deploy --app agent-chat-mikesailab

# Rotate the password
fly secrets set AGENT_CHAT_BASIC_AUTH_PASSWORD='new-pw' --app agent-chat-mikesailab

# Tail logs
fly logs --app agent-chat-mikesailab

# SSH into the machine (e.g. to inspect /data/chat.db)
fly ssh console --app agent-chat-mikesailab
```

## Seeding conversations on the public deploy

The deploy starts with an empty DB. Two ways to add content:

1. **Run `start_conversation.py` against a local DB, then upload it.**
   `fly ssh console`, then `cat > /data/chat.db` from a local copy via
   `fly ssh sftp shell` (or just `fly ssh console -C "..."`).
2. **Future**: Web UI seed-conversation form (Roadmap item). Once that
   ships, you can seed directly through the deployed UI.

For v1 (empty DB), there's nothing to seed — visitors see the
"No conversations yet" state, which is fine for a "this is what the app
looks like" demo.

## Cost expectations

The VM is `shared-cpu-1x` 256 MB with auto-stop. Idle-stopped machines
don't bill compute, so the steady-state cost is just the 1 GB volume
($0.15/mo). First HTTP request after idle warms the machine in ~5s.

If you push it past Fly's free allowance (3 shared VMs, 3 GB volume,
160 GB outbound), Fly bills the overage. For a low-traffic personal demo
you'll stay in the free tier.
