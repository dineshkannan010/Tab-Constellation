"""Ingestion routes — write payloads from the extension to JSONL on disk.

Storage is intentionally dumb (append-only JSONL) until Qdrant lands.
Schemas match what `/extension/background.js` posts — keep them in sync.

Security (kept lean — local-only tool, single user):
  • Every string field has a max_length cap to bound disk + memory use.
  • The screenshot filename is generated server-side (UUID), never built
    from client input — prevents path traversal via crafted timestamps.
  • Timestamps are parsed as real datetimes (rejects malformed input).
"""

from __future__ import annotations

import base64
import binascii
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Literal, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException
from pydantic import AwareDatetime, BaseModel, Field

from routes.ingest_realtime import process_tab

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SCREENSHOT_DIR = DATA_DIR / "screenshots"
TABS_FILE = DATA_DIR / "tabs.jsonl"
EVENTS_FILE = DATA_DIR / "events.jsonl"
HISTORY_FILE = DATA_DIR / "history.jsonl"
SCREENSHOTS_META_FILE = DATA_DIR / "screenshots.jsonl"

# Caps roughly chosen so a single screenshot POST stays under the 5 MB
# request body limit set in main.py. 4 MB of base64 ≈ 3 MB raw JPEG.
MAX_URL = 2048
MAX_TITLE = 1024
MAX_DOMAIN = 255
MAX_META_DESC = 4096
MAX_DOM_SNIPPET = 2000
MAX_SCREENSHOT_B64 = 4_000_000
MAX_HISTORY_BATCH = 100
MAX_H1 = 300
MAX_PATH_TOKENS = 300
MAX_OG_SITE_NAME = 200


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


def append_jsonl(path: Path, obj: dict) -> None:
    ensure_dirs()
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("rb") as f:
        return sum(1 for _ in f)


# --------------------------- models ---------------------------


class TabPayload(BaseModel):
    tab_id: int
    window_id: int
    opener_tab_id: Optional[int] = None
    session_id: UUID
    url: str = Field(..., max_length=MAX_URL)
    domain: str = Field("", max_length=MAX_DOMAIN)
    title: str = Field("", max_length=MAX_TITLE)
    meta_description: Optional[str] = Field(None, max_length=MAX_META_DESC)
    dom_snippet: str = Field("", max_length=MAX_DOM_SNIPPET)
    # New extraction fields — all optional for back-compat with older clients
    og_title: Optional[str] = Field(None, max_length=MAX_TITLE)
    og_description: Optional[str] = Field(None, max_length=MAX_META_DESC)
    og_site_name: Optional[str] = Field(None, max_length=MAX_OG_SITE_NAME)
    h1: Optional[str] = Field(None, max_length=MAX_H1)
    path_tokens: str = Field("", max_length=MAX_PATH_TOKENS)
    timestamp: AwareDatetime
    event_type: Literal["tab_loaded", "history_backfill"]
    youtube_data: Optional[dict] = None


class EventPayload(BaseModel):
    tab_id: int
    window_id: int
    session_id: UUID
    event_type: Literal["tab_created", "tab_activated", "tab_closed"]
    timestamp: Optional[AwareDatetime] = None
    url: Optional[str] = Field(None, max_length=MAX_URL)


class ScreenshotPayload(BaseModel):
    tab_id: int
    window_id: int
    session_id: UUID
    url: str = Field(..., max_length=MAX_URL)
    screenshot_b64: str = Field(..., min_length=1, max_length=MAX_SCREENSHOT_B64)
    timestamp: Optional[AwareDatetime] = None


class HistoryItem(BaseModel):
    url: str = Field(..., max_length=MAX_URL)
    title: str = Field("", max_length=MAX_TITLE)
    last_visit_time: AwareDatetime
    visit_count: int = 0
    typed_count: int = 0
    domain: str = Field("", max_length=MAX_DOMAIN)


class HistoryBatch(BaseModel):
    session_id: UUID
    items: List[HistoryItem] = Field(..., min_length=1, max_length=MAX_HISTORY_BATCH)


# --------------------------- router ---------------------------


router = APIRouter(prefix="/ingest", tags=["ingest"])


def _serialize(payload: BaseModel) -> dict:
    record = payload.model_dump(mode="json")
    record["received_at"] = datetime.now(timezone.utc).isoformat()
    if record.get("timestamp") is None:
        record["timestamp"] = datetime.now(timezone.utc).isoformat()
    return record


@router.post("/tab")
def ingest_tab(payload: TabPayload) -> dict:
    append_jsonl(TABS_FILE, _serialize(payload))
    process_tab(payload.model_dump(mode="json"))   # ← your pipeline
    return {"status": "ok", "received": {"tab_id": payload.tab_id, "url": payload.url}}


@router.post("/event")
def ingest_event(payload: EventPayload) -> dict:
    append_jsonl(EVENTS_FILE, _serialize(payload))
    return {
        "status": "ok",
        "received": {"event_type": payload.event_type, "tab_id": payload.tab_id},
    }


@router.post("/screenshot")
def ingest_screenshot(payload: ScreenshotPayload) -> dict:
    try:
        raw = base64.b64decode(payload.screenshot_b64, validate=True)
    except (binascii.Error, ValueError) as e:
        raise HTTPException(status_code=400, detail=f"invalid base64: {e}")

    ensure_dirs()
    # Server-generated filename only — never trust client timestamp here.
    filename = f"{payload.tab_id}_{uuid4().hex}.jpg"
    file_path = SCREENSHOT_DIR / filename
    # Final defense-in-depth: resolve and ensure we're still inside SCREENSHOT_DIR.
    resolved = file_path.resolve()
    if SCREENSHOT_DIR.resolve() not in resolved.parents:
        raise HTTPException(status_code=400, detail="path traversal blocked")
    resolved.write_bytes(raw)

    meta = {
        "tab_id": payload.tab_id,
        "window_id": payload.window_id,
        "session_id": str(payload.session_id),
        "url": payload.url,
        "file": resolved.relative_to(DATA_DIR).as_posix(),
        "bytes": len(raw),
        "timestamp": payload.timestamp.isoformat(),
        "received_at": datetime.now(timezone.utc).isoformat(),
    }
    append_jsonl(SCREENSHOTS_META_FILE, meta)
    return {"status": "ok", "received": {"file": meta["file"], "bytes": len(raw)}}


@router.post("/history-batch")
def ingest_history_batch(batch: HistoryBatch) -> dict:
    received_at = datetime.now(timezone.utc).isoformat()
    session_id = str(batch.session_id)
    for item in batch.items:
        record = item.model_dump(mode="json")
        record["session_id"] = session_id
        record["received_at"] = received_at
        append_jsonl(HISTORY_FILE, record)
    return {"status": "ok", "received": {"count": len(batch.items)}}


@router.get("/stats")
def ingest_stats() -> dict:
    return {
        "tabs": count_lines(TABS_FILE),
        "events": count_lines(EVENTS_FILE),
        "screenshots": count_lines(SCREENSHOTS_META_FILE),
        "history": count_lines(HISTORY_FILE),
    }