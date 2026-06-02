# Tab Constellation

> Your browsing history as a navigable cognitive map.

A Chrome extension that visualizes browsing history as a 3D semantic
constellation. Built for a Qdrant hackathon.

This repo contains three pieces that talk to each other locally:

| Folder       | What it is                                  | Runs on   |
|--------------|---------------------------------------------|-----------|
| `extension/` | Manifest V3 Chrome extension (toolbar icon) | Chrome    |
| `web/`       | Vite + React + TypeScript frontend          | `:5173`   |
| `api/`       | FastAPI backend                             | `:8000`   |

## Prerequisites

- Node.js 18+
- Python 3.11+
- Docker Desktop (running) — runs Qdrant + Neo4j
- Google Chrome or Brave (any Chromium browser that supports MV3)

## Setup

Two commands get everything running. From the repo root:

```bash
node scripts/setup.mjs    # one time — venv + Python deps + npm install
node scripts/dev.mjs      # start everything (databases + all services)
```

`dev.mjs` starts Qdrant + Neo4j in Docker, waits for them to be healthy, then
launches the Ingest API (`:8000`), Search API (`:8001`), Event Processor, and
the frontend (`:5173`) — all in one terminal. Press `Ctrl+C` to stop them.

Then load the extension:

1. Open `chrome://extensions` (or `brave://extensions`).
2. Toggle **Developer mode** on.
3. Click **Load unpacked** and select the `extension/` folder.
4. Open <http://localhost:5173> and browse a few tabs to populate the constellation.

**📖 For the full walkthrough — every step, the manual (no-scripts) path, and
troubleshooting — see [`SETUP.md`](./SETUP.md).**

## Verifying the full chain

1. Services running (`node scripts/dev.mjs` prints **✓ All services ready**), extension loaded.
2. Click the Tab Constellation icon in the toolbar → a tab opens at <http://localhost:5173>.
3. Browse a few tabs; they appear in the `[ingest]` logs and render as stars.

If the extension badge says **✗ Backend offline**, make sure the Ingest API is
running on port 8000.

## Security

See [`SECURITY.md`](./SECURITY.md). TL;DR: the API binds to loopback only,
incognito tabs are skipped, and `api/data/` plus secrets are gitignored.
This is a local single-user tool, so `/ingest/*` routes are unauthenticated.

## Status
End-to-end pipeline working: the extension captures tabs → the API embeds
them and classifies clusters → data lands in Qdrant (vectors) + Neo4j (graph)
→ the frontend renders the 3D constellation with semantic search.
