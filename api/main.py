"""Tab Constellation API entrypoint.

Security:
  • Bind to 127.0.0.1 only (loopback). See api/README.md for the run cmd.
  • CORS is restricted to the local web app origin. The Chrome extension
    bypasses CORS via host_permissions, so chrome-extension://* origins
    are NOT in the allow-list (and don't need to be).
  • Request bodies are capped at MAX_BODY_BYTES to bound memory use.
  • All /ingest/* models validate field lengths and aware timestamps.
"""

from __future__ import annotations

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from routes.ingest import ensure_dirs, router as ingest_router

# Load api/.env if present (kept around for future env config, e.g. Qdrant URL).
load_dotenv()

MAX_BODY_BYTES = 5 * 1024 * 1024  # 5 MB; screenshot field is capped at ~4 MB.

app = FastAPI(title="Tab Constellation API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def limit_body_size(request: Request, call_next):
    cl = request.headers.get("content-length")
    if cl is not None:
        try:
            if int(cl) > MAX_BODY_BYTES:
                return JSONResponse(
                    status_code=413, content={"detail": "request body too large"}
                )
        except ValueError:
            return JSONResponse(
                status_code=400, content={"detail": "invalid content-length"}
            )
    return await call_next(request)


@app.on_event("startup")
def _startup() -> None:
    ensure_dirs()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(ingest_router)

from qdrant_search_api import router as qdrant_router
app.include_router(qdrant_router)