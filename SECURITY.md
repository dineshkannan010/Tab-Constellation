# Security model

Tab Constellation is a single-developer local tool. It captures
potentially sensitive data — URLs, page titles, DOM text, screenshots,
and 30 days of browser history — and stores it on disk under
`api/data/`. This document describes what we defend against and what we
don't.

## Threat model

| Threat | Defended? | How |
|---|---|---|
| The repository leaking sensitive data to GitHub | ✅ | `.gitignore` blocks `api/data/`, `.env`, `.env.*`, `*.token`, `*.pem`, `*.key`, `secrets/`, `credentials.json`. Verified — git history is clean. |
| A malicious website POSTing to the API from the user's browser | ✅ | CORS only allows `http://localhost:5173`. JSON-content-type requests are non-simple, so the browser preflights and blocks cross-origin POSTs. |
| The API being reachable from the network | ✅ | API binds to `127.0.0.1` only (see README run command). |
| Path traversal via crafted payloads | ✅ | Screenshot filenames are server-generated (UUID); a defense-in-depth resolve-check rejects anything that would escape the screenshot dir. |
| Resource exhaustion via huge requests | ✅ | 5 MB request body cap + per-field `max_length` on Pydantic models. |
| Capturing incognito browsing | ✅ | Background SW skips tabs / windows where `tab.incognito === true`. |
| Capturing pages with extension scheme (chrome://, about:) | ✅ | Content script bails on those URLs; SW filters to `http(s)` only. |

## What we explicitly do NOT defend against

- **Bearer-token auth on the API.** Considered and deferred: while the
  app stays single-user / local-dev, anything on `127.0.0.1` (other
  local apps, other Chrome extensions installed in the same profile)
  can POST to `/ingest/*`. Add token auth before shipping this to
  anyone else, or before running it on a shared machine.
- **Encryption at rest.** Tabs, screenshots, and history are stored as
  plaintext JSONL / JPEG under `api/data/`. Anyone with read access to
  your home directory can read them.
- **An attacker with code execution on your machine.** They can read
  `api/data/` and your Chrome profile directly.
- **Sensitive-domain blocklist.** We do not skip banking, email, or
  password-manager pages. If you want this, add a hostname blocklist
  in `extension/background.js` (and `content_script.js`).
- **Network sniffing.** API traffic is HTTP, not HTTPS. We rely on the
  loopback bind for confidentiality.

## Reporting an issue

Open a GitHub issue or contact the maintainer directly. Do not include
data captured in `api/data/` — it is private.
