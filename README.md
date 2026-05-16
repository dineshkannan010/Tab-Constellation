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
- Google Chrome (or any Chromium-based browser that supports MV3)

## Running it locally

Open three terminals — one for the backend, one for the frontend, and
Chrome itself for the extension.

### 1. Backend (`api/`)

```bash
cd api
python -m venv .venv
# Windows PowerShell:  .\.venv\Scripts\Activate
# macOS / Linux:       source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Sanity check: `http://localhost:8000/health` → `{"status":"ok"}`.

### 2. Frontend (`web/`)

```bash
cd web
npm install
npm run dev
```

Opens at `http://localhost:5173`. In the corner you should see
**✓ Backend connected** (assuming the API from step 1 is running).

### 3. Extension (`extension/`)

1. Open `chrome://extensions`.
2. Toggle **Developer mode** on.
3. Click **Load unpacked** and select the `extension/` folder.
4. The Tab Constellation icon appears in the toolbar.

## Verifying the full chain

1. Backend running on `:8000`, frontend running on `:5173`, extension loaded.
2. Click the Tab Constellation icon in the Chrome toolbar.
3. A new tab opens at `http://localhost:5173`.
4. The hero **Tab Constellation** + tagline renders.
5. Top-right badge reads **✓ Backend connected**.

If the badge says **✗ Backend offline**, the API isn't reachable —
make sure `uvicorn` is running on port 8000.

## Status
Skeleton only created for now. No vector search, no embeddings, no 3D rendering
yet. The constellation view is a placeholder.
