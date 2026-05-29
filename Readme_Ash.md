# Tab Constellation 🌌

> Your browsing history as an immersive 3D cognitive map — powered by Qdrant vector search.

Tab Constellation captures every tab you open, understands what you were doing (research, work, entertainment, social), and visualizes your entire browsing universe as a rotating 3D constellation. Semantic search lets you find any page by meaning, not just keywords. Scroll down to explore rabbit holes, distraction fingerprints, and your mission control dashboard.

---

## What You'll See

| Section | What it shows |
|---------|--------------|
| 🌌 Constellation | Every tab as a star, colored by cluster, connected by session |
| 🐇 The Wormhole | Your deepest rabbit hole — the chain of tabs that took you off course |
| 💥 The Crash Site | Distraction fingerprint — where your focus went |
| 🧠 Mission Control | Focus score, time breakdown, browsing signature |
| 🌑 The Void | Tabs you opened and never came back to |

---

## Prerequisites

- macOS or Linux (Windows works with minor path changes)
- Python 3.11+
- Node.js 18+
- Docker Desktop (running)
- Brave or Chrome browser

---

## Step 1 — Clone the repo

```bash
git clone https://github.com/YOUR_USERNAME/tab_constellation.git
cd tab_constellation
```

---

## Step 2 — Pull and start Docker services

These run in the background. Anyone can use these commands — credentials are intentionally simple for local use.

```bash
# Qdrant — vector database (stores tab embeddings)
docker run -d \
  --name qdrant \
  -p 6333:6333 \
  qdrant/qdrant

# Neo4j — graph database (stores tab relationships)
docker run -d \
  --name neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/constellation \
  neo4j:5
```

Verify both are running:
```bash
docker ps
```

You should see both `qdrant` and `neo4j` in the list.

> **Note:** The credentials `neo4j/constellation` are hardcoded throughout the codebase. Anyone running locally uses the same credentials — this is fine since it's a local-only tool.

---

## Step 3 — Python backend setup

```bash
cd api
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

pip install -r requirements.txt
pip install \
  sentence-transformers \
  neo4j \
  qdrant-client \
  transformers \
  torch \
  python-dotenv
```

> First run downloads two ML models (~450MB total, one-time only):
> - `all-MiniLM-L6-v2` — embedding model for vector search
> - `cross-encoder/nli-MiniLM2-L6-H768` — classification model

---

## Step 4 — Frontend setup

```bash
cd web
npm install
```

---

## Step 5 — Run everything (6 terminals)

Open 6 terminal tabs/windows. Run one command per terminal.

**Terminal 1 — Ingest API** (receives tabs from extension)
```bash
cd tab_constellation/api
source venv/bin/activate
uvicorn main:app --reload --port 8000
```

**Terminal 2 — Search API** (serves data to frontend)
```bash
cd tab_constellation/api
source venv/bin/activate
uvicorn qdrant_search_api:app --reload --port 8001
```

**Terminal 3 — Event Processor** (computes time spent + depth every 20s)
```bash
cd tab_constellation/api
source venv/bin/activate
python event_processor.py --watch --interval 20
```

**Terminal 4 — Frontend**
```bash
cd tab_constellation/web
npm run dev
```

Terminals 5 & 6 are your Docker services from Step 2 — they run in the background, no terminal needed if you used `-d`.

### Verify everything is running

```bash
curl http://localhost:8000/health   # → {"status":"ok"}
curl http://localhost:8001/health   # → {"status":"ok","collection":"tab_constellation"}
curl http://localhost:6333/healthz  # → {"title":"qdrant - vector search engine"}
```

---

## Step 6 — Install the Chrome Extension

1. Open Brave or Chrome and go to:
   ```
   brave://extensions    (Brave)
   chrome://extensions   (Chrome)
   ```

2. Toggle **Developer mode** ON (top right corner)

3. Click **Load unpacked**

4. Navigate to the cloned repo and select the `extension/` folder

5. You should see **Tab Constellation 0.1.0** appear in the list

6. Pin it to your toolbar: click the puzzle piece icon → pin Tab Constellation

7. Click the extension icon — the popup should show **Backend connected ✓**

---

## Step 7 — Open the app

Go to: **http://localhost:5173**

Browse 10–15 tabs in Brave/Chrome normally. Each tab is ingested in real-time — you'll see it appear in Terminal 1:

```
✓ [new][research][distraction=False] Qdrant Documentation
✓ [new][work][distraction=False] GitHub - your-repo
✓ [new][entertainment][distraction=True] YouTube
```

Refresh the constellation to see your tabs as stars.

---

## How it works

```
You browse in Brave/Chrome
        ↓
Extension captures tab URL, title, page content
        ↓
POST /ingest/tab → FastAPI (port 8000)
        ↓
NLI classifier → assigns cluster (research/work/entertainment/...)
Content-aware distraction detection
384-dim embedding generated
        ↓
Stored in Qdrant (vectors) + Neo4j (graph relationships)
        ↓
Frontend fetches from port 8001
Three.js renders your constellation
```

---

## Semantic Search

Type any concept in the search bar and hit Enter (or click SCAN). Matching nodes glow white, everything else dims. This uses Qdrant vector search — it finds meaning, not keywords.

Examples to try:
- `machine learning` — finds all ML-related tabs
- `golang backend` — finds Go-related tabs even if the title says "gRPC"
- `procrastination` — finds YouTube, Reddit, entertainment tabs

---

## Features

| Feature | How to access |
|---------|--------------|
| Semantic search | Search bar, top left |
| Cluster filter | Buttons, top right |
| Time window | Slider (1–90 days) |
| Focus summary | 🧠 FOCUS button |
| Rabbit holes | 🐇 RABBIT button |
| Distraction fingerprint | ⚡ DISTRACTION button |
| Node detail | Click any star |
| 3D rotation | Click and drag |
| Zoom | Scroll wheel |
| Sections | Scroll down |

---

## Troubleshooting

**"Backend offline" in extension popup**
→ Make sure Terminal 1 (port 8000) is running

**Constellation shows "No nodes" or is empty**
→ Browse a few tabs first, then hard refresh (Cmd+Shift+R)

**Search returns no results**
→ Check port 8001 is running: `curl http://localhost:8001/health`
→ Make sure `ENVIRONMENT = Environment.PRODUCTION` in `api/qdrant_config.py`

**Neo4j connection error in Terminal 1**
→ Check Docker: `docker ps | grep neo4j`
→ Restart if needed: `docker start neo4j`

**"Collection doesn't exist" error**
→ Browse one tab — the collection is auto-created on first ingest

**Models downloading slowly**
→ First run only. Set `HF_TOKEN` to avoid rate limits:
```bash
export HF_TOKEN=your_token_here  # get free token at huggingface.co
```

**Reset everything (fresh start)**
```bash
curl -X DELETE http://localhost:6333/collections/tab_constellation
docker exec -it neo4j cypher-shell -u neo4j -p constellation "MATCH (n) DETACH DELETE n"
rm api/data/tabs.jsonl api/data/events.jsonl
touch api/data/tabs.jsonl api/data/events.jsonl
# Then restart Terminal 1
```

---

## Data & Privacy

All data stays **100% local** on your machine:
- Qdrant runs in Docker on `localhost:6333`
- Neo4j runs in Docker on `localhost:7687`
- No data is sent to any external server
- Tab data is stored in `api/data/` as JSONL files

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Vector DB | Qdrant |
| Graph DB | Neo4j |
| Embeddings | sentence-transformers/all-MiniLM-L6-v2 |
| Classification | cross-encoder/nli-MiniLM2-L6-H768 |
| Backend | FastAPI + Python |
| Frontend | React + Three.js + Vite |
| Extension | Chrome MV3 |

---

## Built for Qdrant Hackathon 2026

Tab Constellation demonstrates a new kind of interaction with vector search — not Q&A, but **spatial cognition**. Your browsing history becomes a navigable 3D universe where semantic similarity determines proximity, and every distraction leaves a visible trace.