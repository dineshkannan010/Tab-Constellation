# Tab Constellation — API

FastAPI backend. Single `GET /health` route for now.

## Setup (Windows, PowerShell)

```powershell
cd api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Setup (macOS / Linux)

```bash
cd api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run the server

```bash
uvicorn main:app --reload --port 8000
```

Then visit `http://localhost:8000/health` — expect `{"status":"ok"}`.

## CORS

The dev server allows requests from `http://localhost:5173` (the Vite
dev server) and any `chrome-extension://…` origin.
