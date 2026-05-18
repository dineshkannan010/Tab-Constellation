# Data contract — DO NOT BREAK without re-signing

This file is the contract between the **ingest pipeline** (the
extension + `api/routes/ingest.py`, owner: Dinesh) and any downstream
consumer that builds graph edges, vector indexes, or insights from
this data (teammate 2: Neo4j edges, Qdrant collections, /search,
/graph-expand, /insights).

The two payload schemas below are **locked**. Field names, types, and
event-type enum values are part of the contract. Renaming or
re-typing any locked field requires both signers below to acknowledge
the change before it merges.

> If field names drift from what the edge-creation code expects,
> integration day is a graveyard. We are signing this now precisely so
> that doesn't happen.

---

## `POST /ingest/tab` — LOCKED

Sent by the extension once per "tab_loaded" (or per "history_backfill"
row) with full content for embedding and edge construction.

```jsonc
{
  "tab_id":           number,            // chrome.tabs.Tab.id, unique within a browser session
  "window_id":        number,            // chrome.tabs.Tab.windowId
  "opener_tab_id":    number | null,     // chrome.tabs.Tab.openerTabId — drives OPENED_AFTER edges
  "session_id":       string (UUID v4),  // one browser session = one UUID; drives SAME_SESSION edges
  "url":              string,            // full URL, max 2048 chars
  "domain":           string,            // parsed from URL hostname, max 255 chars
  "title":            string,            // document.title, max 1024 chars
  "meta_description": string | null,     // meta[name="description"], max 4096 chars
  "dom_snippet":      string,            // body.innerText collapsed + sliced to 500 chars (capped at 2000 server-side)
  "timestamp":        string (ISO 8601, aware), // when the tab finished loading; this is the "opened_at" for OPENED_AFTER
  "event_type":       "tab_loaded" | "history_backfill"
}
```

Stored at `api/data/tabs.jsonl`, one JSON object per line.
Each on-disk row additionally carries `"received_at"` (server wall
clock ISO 8601). `received_at` is **not** part of the locked contract —
treat it as a debug field; don't build edges on it.

## `POST /ingest/event` — LOCKED

Lightweight, no content. Sent for tab lifecycle transitions.

```jsonc
{
  "tab_id":     number,
  "window_id":  number,
  "session_id": string (UUID v4),
  "event_type": "tab_created" | "tab_activated" | "tab_closed",
  "timestamp":  string (ISO 8601, aware),
  "url":        string | null            // null for tab_created (URL not known yet); best-effort otherwise
}
```

Stored at `api/data/events.jsonl`, one JSON object per line.
Same `received_at` debug field as above.

---

## Neo4j edge → field mapping

The edge-builder MUST read these fields from these endpoints. If you
want a field that isn't here, file an issue against this doc first —
don't quietly add it on the consumer side.

| Edge                  | Required fields                                          | Source rows                                                                 |
|-----------------------|----------------------------------------------------------|-----------------------------------------------------------------------------|
| `OPENED_AFTER`        | `opener_tab_id` (source) → `tab_id` (target), `timestamp` | `/ingest/tab` rows where `event_type == "tab_loaded"` and `opener_tab_id != null` |
| `OPEN_SIMULTANEOUSLY` | `window_id` (must match between two tabs), `timestamp`   | `/ingest/event` `tab_activated` / `tab_closed` pairs → compute overlap windows |
| `SAME_SESSION`        | `session_id` (must match)                                | Any row from either endpoint                                                |

Notes for the edge builder:

- `tab_id` is **not** globally unique — it's unique within one
  `session_id`. Always key on `(session_id, tab_id)`.
- `window_id` is similarly only unique within a session.
- `timestamp` is always aware ISO 8601 (the server rejects naive
  timestamps with 422). Safe to parse with any ISO 8601 lib.
- `tab_loaded` rows fire after the page finishes loading
  (`changeInfo.status === "complete"`). Use this as "opened_at" for
  `OPENED_AFTER`.
- The extension currently skips incognito tabs entirely — they will
  never appear in any row.
- The extension does NOT capture chrome://, chrome-extension://, or
  about: URLs — they will not appear in any row.

---

## Other endpoints (informational — not part of the lock)

These are owned by ingest and may evolve. The graph builder is free to
consume them but should not pin to specific field names yet.

- `POST /ingest/screenshot` — JPEG bytes (base64), tab/window/session
  ids, url, timestamp. JPEGs land in `api/data/screenshots/`; metadata
  in `api/data/screenshots.jsonl`.
- `POST /ingest/history-batch` — list of `{url, title, last_visit_time,
  visit_count, typed_count, domain}` items + `session_id`. Stored at
  `api/data/history.jsonl`.
- `GET /ingest/stats` — debug counts.

If you start building edges that depend on fields from these, move
them under "LOCKED" above and re-sign.

---

## Change process

1. Open a PR that updates this file *and* the affected schemas /
   consumers in the same commit.
2. Both signers below must re-acknowledge in the PR description before
   merge. New `event_type` enum values count as changes.
3. Bump the **Schema version** below by one.

**Schema version:** 1
**Last changed:** 2026-05-18

---

## Sign-off

By signing below, you acknowledge that the locked schemas above
reflect what your code reads from / writes to disk.

- [ ] **Ingest pipeline owner** — Dinesh K — date: ____________
- [ ] **Graph / search owner** — _________________ — date: ____________
