# Tab Constellation 🌌

> Your browsing history as a navigable cognitive map.

A Chrome extension that visualizes your browsing history as a 3D semantic
constellation. Built for a Qdrant hackathon.

The extension captures the tabs you visit → the API embeds and classifies them
→ data lands in **Qdrant** (vectors) + **Neo4j** (graph) → the frontend renders
an interactive 3D constellation with semantic search.
Works on **macOS, Linux, and Windows**.

YouTube Demo Link - <https://www.youtube.com/watch?v=H8YAxR0m23g>

<p align="center">
  <img src="https://github.com/user-attachments/assets/b1d8d539-e126-41f6-92a6-24a4c09a963a" alt="Tab Constellation Architecture" width="700"/>
</p>
---

## What you'll be running

Everything runs on your local machine. The two databases run in Docker;
everything else runs natively and talks to them over `localhost`.

| Piece | Where it runs | What it does |
|-------|---------------|--------------|
| **Qdrant** | Docker, `:6333` | Vector database — stores tab embeddings |
| **Neo4j** | Docker, `:7687` (UI `:7474`) | Graph database — stores tab relationships |
| **Ingest API** | Python, `:8000` | Receives tabs from the extension |
| **Search API** | Python, `:8001` | Serves data to the frontend |
| **Event Processor** | Python (background) | Computes time-spent + depth every 20s |
| **Frontend** | Vite, `:5173` | React + Three.js constellation UI |
| **Extension** | Your browser | Captures the tabs you visit |

---

## Prerequisites

Install these first:

- **Node.js 18+** — <https://nodejs.org>
- **Python 3.11+** — <https://www.python.org/downloads/>
- **Docker Desktop** (must be **running** before you start) — <https://www.docker.com/products/docker-desktop/>
- **A Chromium browser** — Google Chrome or Brave (any browser supporting MV3)

Verify each is available:

```bash
node --version      # v18 or higher
python3 --version   # 3.11 or higher  (Windows: python --version)
docker --version    # any recent version
docker info         # should succeed — confirms the daemon is running
```

> **Windows note:** use `python` instead of `python3` if that's how Python is
> on your PATH. The setup script auto-detects either.

---

## The fast path (two commands)

If you just want it running:

```bash
# 1. Clone and enter the repo
git clone <repo-url>
cd Tab-Constellation

# 2. One-time install (venv + Python deps + npm)
node scripts/setup.mjs

# 3. Start everything (databases + all services)
node scripts/dev.mjs
```

Then [load the extension](#step-4--load-the-browser-extension) and
[open the app](#step-5--open-the-app-and-browse). That's it — the rest of this
guide explains each step in detail and covers troubleshooting.

---

## Step 1 — Clone the repository

```bash
git clone <repo-url>
cd Tab-Constellation
```

---

## Step 2 — Install dependencies (one time)

```bash
node scripts/setup.mjs
```

This script:

1. Finds a Python ≥ 3.11 on your system (override with `PYTHON=python3.12 node scripts/setup.mjs`).
2. Creates the Python virtual environment at `api/venv`.
3. Installs the Python dependencies, including the ML libraries
   (`sentence-transformers`, `transformers`, `torch`, `qdrant-client`, `neo4j`).
4. Runs `npm install` in `web/`.
5. Creates `api/.env` with the Neo4j password (`NEO4J_PASSWORD=constellation`).

> **First run is slow.** Installing `torch` and the ML libraries downloads a few
> hundred MB. This only happens once.

---

## Step 3 — Start all the services

```bash
node scripts/dev.mjs
```

This script:

1. Checks Docker is installed and running.
2. Starts Qdrant + Neo4j via `docker compose up -d` and waits until both are healthy.
3. Launches the four app processes — Ingest API, Search API, Event Processor,
   and the frontend — each with a colored log prefix so you can tell them apart:
   `[ingest]` `[search]` `[events]` `[web]`.
4. Confirms the APIs respond, then prints **✓ All services ready**.

Leave this terminal open — all the logs stream here. **Press `Ctrl+C` to stop
everything.**

When it's ready you should see something like:

```
Waiting for Qdrant (http://localhost:6333/healthz) ✓
Waiting for Neo4j (http://localhost:7474) ✓
...
✓ All services ready.
  App:        http://localhost:5173
```

### Verify it yourself (optional)

```bash
curl http://localhost:8000/health   # {"status":"ok"}
curl http://localhost:8001/health   # {"status":"ok","collection":"tab_constellation"}
curl http://localhost:6333/healthz  # healthz check passed
```

---

## Step 4 — Load the browser extension

This step is **manual** — browsers require a human to load an unpacked
extension (there's no way to script it).

1. Open your browser's extensions page:
   - Chrome: `chrome://extensions`
   - Brave: `brave://extensions`
2. Toggle **Developer mode** **ON** (top-right corner).
3. Click **Load unpacked**.
4. Select the **`extension/`** folder inside this repo.
5. **Tab Constellation 0.1.0** appears in your extensions list.
6. Pin it: click the puzzle-piece icon in the toolbar → pin **Tab Constellation**.
7. Click the extension icon — the popup should show **Backend connected ✓**.

---

## Step 5 — Open the app and browse

1. Go to **<http://localhost:5173>**.
2. Browse 10–15 tabs normally in your browser. Each tab is ingested in
   real time — you'll see it appear in the `[ingest]` logs:

   ```
   ✓ [new][research][distraction=False] Qdrant Documentation
   ✓ [new][work][distraction=False] GitHub - your-repo
   ✓ [new][entertainment][distraction=True] YouTube
   ```

3. Refresh the constellation to see your tabs render as stars.

> **First ingest is slow.** The first time a tab is processed, ~450 MB of ML
> models download (`all-MiniLM-L6-v2` for embeddings and a classifier). This is
> a one-time download.

---

## Stopping everything

- **Stop the app processes:** press `Ctrl+C` in the `node scripts/dev.mjs` terminal.
- **Stop the databases too:**

  ```bash
  docker compose down        # keeps your data
  docker compose down -v     # also deletes the database volumes (wipes data)
  ```

---

## Manual setup (without the scripts)

The scripts are just convenience wrappers. If you prefer to run things by hand:

**Start the databases:**

```bash
docker compose up -d
```

**Install (one time):**

```bash
cd api
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt sentence-transformers neo4j qdrant-client transformers torch python-dotenv
echo "NEO4J_PASSWORD=constellation" > .env

cd ../web && npm install
```

**Run the four services (one terminal each):**

```bash
# Terminal 1 — Ingest API
cd api && source venv/bin/activate && uvicorn main:app --reload --port 8000

# Terminal 2 — Search API
cd api && source venv/bin/activate && uvicorn qdrant_search_api:app --reload --port 8001

# Terminal 3 — Event Processor
cd api && source venv/bin/activate && python event_processor.py --watch --interval 20

# Terminal 4 — Frontend
cd web && npm run dev
```

Then load the extension (Step 4) and open the app (Step 5).

---

## Troubleshooting

**`Docker is not installed` / `daemon is not running`**
→ Install Docker Desktop and make sure it's open. Confirm with `docker info`.

**Extension popup says "Backend offline"**
→ Make sure the Ingest API (`:8000`) is running. Check the `[ingest]` logs.

**Constellation shows "No nodes" / is empty**
→ Browse a few tabs first, then hard-refresh the page (Cmd/Ctrl+Shift+R).

**Search returns no results / `Collection doesn't exist`**
→ The Qdrant collection is auto-created on the first ingest. Browse one tab,
then retry. Also confirm the Search API is up: `curl http://localhost:8001/health`.

**`Python venv not found`**
→ Run `node scripts/setup.mjs` first.

**Port already in use (8000 / 8001 / 5173 / 6333 / 7687)**
→ Another process is using it. Stop it, or stop a previous run
(`Ctrl+C` the dev script, then `docker compose down`).

**Neo4j connection error**
→ Check the container: `docker ps | grep neo4j`. Restart with
`docker compose up -d`. The password must be `constellation` (in `api/.env`).

**Models downloading slowly**
→ First run only. To avoid HuggingFace rate limits, set a free token:

```bash
export HF_TOKEN=your_token_here   # get one free at huggingface.co
```

(The dev script passes your environment through, so this just works.)

**Reset everything (fresh start)**

```bash
curl -X DELETE http://localhost:6333/collections/tab_constellation
docker exec -it neo4j cypher-shell -u neo4j -p constellation "MATCH (n) DETACH DELETE n"
rm api/data/tabs.jsonl api/data/events.jsonl
# (Windows: del api\data\tabs.jsonl api\data\events.jsonl)
```

Then restart the services.

---

## Data & privacy

Everything stays **100% local**:

- Qdrant runs in Docker on `localhost:6333`.
- Neo4j runs in Docker on `localhost:7687`.
- No data is sent to any external server.
- Raw tab data is stored in `api/data/` as JSONL files.

For the full threat model see [`SECURITY.md`](./SECURITY.md). TL;DR: the API
binds to loopback only, incognito tabs are skipped, and `api/data/` plus
secrets are gitignored. This is a local single-user tool, so `/ingest/*` routes
are unauthenticated.

---

## Status
End-to-end pipeline working: the extension captures tabs → the API embeds
them and classifies clusters → data lands in Qdrant (vectors) + Neo4j (graph)
→ the frontend renders the 3D constellation with semantic search.
