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
- `api/` — FastAPI + uvicorn on `:8000`. One route: `GET /health`.
  CORS allows `http://localhost:5173` and any `chrome-extension://*` origin.

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
