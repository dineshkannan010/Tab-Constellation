# Tab Constellation — Project History (for Claude)

This file is a running log of decisions, context, and progress for the
Tab Constellation project. It is intended to give future Claude
conversations enough context to pick up where the previous one left off
without re-asking the user.

---

## Project at a glance

**What:** A Chrome extension that visualizes browsing history as a 3D
semantic constellation.
**Why:** Hackathon project for Qdrant.
**Tagline:** "Your browsing history as a navigable cognitive map."

## Architecture (current)

Three pieces in one monorepo, all running locally:

- `extension/` — Manifest V3 Chrome extension. Permission: `tabs` only.
  Clicking the toolbar icon opens `http://localhost:5173` in a new tab.
  No popup, no settings UI.
- `web/` — Vite + React + TypeScript + Tailwind v4. Dev server on `:5173`.
  Single landing page; pings `GET /health` on mount and shows a badge.
- `api/` — FastAPI + uvicorn on `:8000`, bound to `127.0.0.1`.
  `GET /health` and all `/ingest/*` routes are unauthenticated (local
  single-user tool). CORS allows `http://localhost:5173` only — the
  extension bypasses CORS via `host_permissions`. Ownership split: this
  assistant owns the ingest pipeline; teammate 2 owns `/search`,
  `/graph-expand`, `/insights`.

## Hard constraints from the user

- **No features beyond what was explicitly requested.** No auth, no DB,
  no Qdrant yet, no extension popup/settings, no testing framework, no
  Storybook, no extra ESLint config, no Husky, no Prettier.
- **No premature dependencies.** Do not install `three`,
  `@react-three/fiber`, `qdrant-client`, `sentence-transformers`, or
  any ML libs until asked.
- Stop after each scaffold step — wait for direction before building
  features.

## History log

### 2026-05-18 — Day 3: security pass (token auth deferred)

Built a fuller security pass first, then user pushed back on the
extension-side token UX for a local single-user dev tool. Kept the
zero-friction hardening, rolled back the token layer.

**Kept:**
- Pydantic models in `routes/ingest.py` use `AwareDatetime` for
  timestamps and `Field(..., max_length=…)` everywhere. Screenshot b64
  capped at ~4 MB; history batch capped at 100 items.
- Screenshot filename is server-generated (`{tab_id}_{uuid4}.jpg`) with
  a resolve-check defense in depth — never derived from client input.
- `main.py` middleware rejects bodies > 5 MB. CORS narrowed to
  `http://localhost:5173` only; `allow_credentials=False`. Extension
  fetches use `host_permissions`, not CORS. README binds via
  `--host 127.0.0.1`.
- Extension tab listeners + screenshot tick skip `tab.incognito === true`.
  PAGE_CONTENT buffer also skips incognito senders.
- `.gitignore` broadened: `.env.*`, `*.token`, `*.pem`, `*.key`,
  `*.p12`, `*.pfx`, `secrets/`, `credentials.json`.
- New: `SECURITY.md` (threat model, with "no API auth" as an explicit
  non-goal). Git history scan on this date: clean — no secrets ever
  committed.

**Rolled back (do NOT re-add without asking):**
- `api/security.py` (token gen + `require_token` dependency)
- `Depends(require_token)` on the `/ingest/*` router
- Extension popup "API token" UI, `api_token` in chrome.storage.local,
  `Authorization: Bearer` header in SW fetches, `POPUP_SET_TOKEN`
  handler, auth_status reporting
- `api/.env.example`

Add the token layer back when (a) the API runs on a shared host, or
(b) we're shipping the extension to anyone but the developer.

### 2026-05-17 — Day 2: capture pipeline

- Extension permissions expanded to `history`, `activeTab`, `scripting`,
  `storage`, `alarms` + `<all_urls>` host. New files:
  `logger.js` (TC: prefix), `content_script.js` (DOM extract on
  document_idle + visibilitychange), `popup.{html,js,css}` (dark UI:
  stats + open / re-backfill / flush / clear buttons), and a full
  rewrite of `background.js` (session id in `chrome.storage.session`,
  tab onCreated/onUpdated/onActivated/onRemoved → POSTs, periodic
  30-s screenshot via `chrome.alarms` + `captureVisibleTab`, history
  backfill on install batched 50/POST with 500 ms delay, retry queue
  capped at 200 with 1-min `chrome.alarms` flush).
- API: split routes into `api/routes/ingest.py`. Added
  `/ingest/{tab,event,screenshot,history-batch,stats}` writing JSONL
  to `api/data/` (and JPEGs to `api/data/screenshots/`). Schemas use
  `session_id: UUID` for validation. `main.py` mounts the router and
  `ensure_dirs()` runs on startup. `api/data/` added to `.gitignore`.

### 2026-05-16 — Day 1: scaffold

- Created repo structure: `extension/`, `web/`, `api/`, plus
  `scripts/make-icons.ps1` (PowerShell + `System.Drawing` to render the
  toolbar PNG icons at 16/32/48/128 px from the same constellation design
  used in `extension/icons/icon.svg`).
- Extension: MV3, `tabs` permission only, background service worker
  opens `http://localhost:5173` on `action.onClicked`.
- Web: Vite scaffold (`react-ts` template), Tailwind v4 via the
  `@tailwindcss/vite` plugin. Removed the Vite demo `App.css`,
  `src/assets/`, and `public/icons.svg`. Replaced `public/favicon.svg`
  with the constellation icon. Landing page = hero + dashed
  "Constellation view — coming soon" placeholder + corner health badge.
- API: Python venv at `api/.venv`, `fastapi` + `uvicorn[standard]` +
  `python-dotenv`. `main.py` exposes `GET /health` with CORS configured.
- Root: `README.md`, `Claude.md` (this file), `.gitignore`.
- Git init / first commit deferred to the user.

## Things to remember for future sessions

- Python is 3.14 on this machine — newer than the 3.11+ minimum the
  README states, but everything installed cleanly.
- Tailwind is v4 (no `tailwind.config.js`; configured via the Vite
  plugin and `@import "tailwindcss";` in `src/index.css`).
- Icon PNGs are generated, not hand-drawn. Re-run
  `powershell -ExecutionPolicy Bypass -File scripts/make-icons.ps1` to
  regenerate after editing the design (mirror any SVG edits in the
  PowerShell script — the script does not parse the SVG).
- When asked for a single bundled feature vs. many small PRs / commits,
  default to asking. The user is intentionally scoping work tightly.
