FROM python:3.12-slim

WORKDIR /app

# System deps:
#  - gcc, libpq-dev: build asyncpg and other native wheels
#  - curl, ca-certificates, gnupg: required to fetch + verify the NodeSource setup script
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl ca-certificates gnupg \
  && rm -rf /var/lib/apt/lists/*

# --- Node.js 20 LTS -----------------------------------------------------------
# Needed at RUNTIME so the Python app can spawn ADK MCP servers as stdio
# subprocesses (e.g. `npx @notionhq/notion-mcp-server`). Installed via the
# NodeSource apt repo, which puts node, npm, and npx on PATH for every process
# in the container — including children spawned by uvicorn.
# Docs: docs/GOOGLE_CLOUD_RUN_DEPLOYMENT.md
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
  && apt-get install -y --no-install-recommends nodejs \
  && rm -rf /var/lib/apt/lists/* \
  && node --version && npm --version && npx --version

# Pre-bake the Notion MCP server into the image. This is deliberate: it means the
# stdio subprocess spawns INSTANTLY at request time instead of doing an `npx -y`
# network fetch on first use, which would stutter during a live demo (and would
# fail entirely if the container had no egress). Add more MCP servers here as
# they're adopted.
RUN npm install -g @notionhq/notion-mcp-server

# --- Python deps --------------------------------------------------------------
# Build context is the repo root (see gcloud-run.sh / `docker build` at repo root).
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code (backend) + GraphQL operations consumed by DataConnectClient at runtime.
COPY backend/ /app/
COPY dataconnect/ /app/dataconnect/

# Cloud Run sets PORT=8080
ENV PORT=8080
EXPOSE 8080

# Python FastAPI entrypoint — UNCHANGED. The app spawns `npx @notionhq/notion-mcp-server`
# as a child process when the ADK MCP tool is invoked; node/npx are already on PATH above.
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT}
