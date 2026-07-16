# Multi-stage build keeps the runtime image lean.
# Stage 1 installs deps with build tools available; stage 2 copies just the
# installed packages over to a slim runtime image.
FROM python:3.13-slim AS deps

WORKDIR /build

# Build deps for any wheels we don't get prebuilt (cffi, cryptography on
# rare arches). Removed implicitly by not carrying this stage forward.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# `pywin32` slips into requirements.txt because the canonical pin set was
# captured on Windows. It has no Linux wheel, and nothing in src/web_ui.py
# imports it, so strip it before install.
RUN grep -v -i '^pywin32' requirements.txt > /tmp/req.txt \
    && pip install --no-cache-dir --prefix=/install -r /tmp/req.txt


FROM python:3.13-slim

WORKDIR /app

COPY --from=deps /install /usr/local
COPY src/ ./src/
# Persona avatar images, served at /avatars/<slug> by web.avatars. Resolved
# relative to the repo root (parents[2] of src/web/avatars.py) → /app/images/...
COPY images/AgentChat-Avatars/ ./images/AgentChat-Avatars/

# Defaults; fly.toml [env] overrides AGENT_CHAT_DB to /data/chat.db so the
# DB lives on the persistent volume. AGENT_CHAT_BASIC_AUTH_PASSWORD is set
# via `fly secrets set`, never baked into the image.
ENV AGENT_CHAT_DB=/data/chat.db \
    HOST=0.0.0.0 \
    PORT=8080 \
    PYTHONUNBUFFERED=1

EXPOSE 8080

CMD ["python", "src/web_ui.py"]
