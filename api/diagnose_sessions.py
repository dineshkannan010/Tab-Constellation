"""
Tab Constellation — Session Diagnostic Script
==============================================
Run from your tab_constellation/api directory with venv activated:

    cd tab_constellation/api
    source venv/bin/activate
    python diagnose_sessions.py

This will tell you exactly why certain nodes show a spider web.
"""

from qdrant_client import QdrantClient
from collections import defaultdict
import json

client = QdrantClient(url="http://localhost:6333")
COLLECTION = "tab_constellation"

# ── 1. Fetch all points ──────────────────────────────────────────────────────
print("\nFetching all points from Qdrant...")
all_points = []
offset = None
while True:
    result, next_offset = client.scroll(
        collection_name=COLLECTION,
        limit=100,
        offset=offset,
        with_payload=True,
        with_vectors=False,
    )
    all_points.extend(result)
    if next_offset is None:
        break
    offset = next_offset

print(f"\n{'='*60}")
print(f"  TOTAL POINTS IN QDRANT: {len(all_points)}")
print(f"{'='*60}")

if not all_points:
    print("  ❌ Collection is empty. Make sure your FastAPI is running and you've ingested tabs.")
    exit()

# ── 2. Show ALL payload keys present (so we know field names) ─────────────────
all_keys = set()
for p in all_points:
    all_keys.update(p.payload.keys())
print(f"\n  Payload fields found: {sorted(all_keys)}")

# ── 3. Find the session_id field name ─────────────────────────────────────────
# Try common variations
SESSION_FIELD = None
for candidate in ["session_id", "sessionId", "session", "browsing_session_id"]:
    if candidate in all_keys:
        SESSION_FIELD = candidate
        break

print(f"  Session field detected: {SESSION_FIELD or '⚠️  NONE FOUND'}")

# ── 4. Group by session ───────────────────────────────────────────────────────
sessions = defaultdict(list)
no_session = []

for p in all_points:
    sid = p.payload.get(SESSION_FIELD) if SESSION_FIELD else None
    if sid:
        sessions[sid].append(p)
    else:
        no_session.append(p)

print(f"\n{'='*60}")
print(f"  SESSION BREAKDOWN")
print(f"{'='*60}")
print(f"  Points WITH a session_id :  {len(all_points) - len(no_session)}")
print(f"  Points with NO session_id:  {len(no_session)}")
print(f"  Unique sessions          :  {len(sessions)}")

# ── 5. Per-session breakdown ──────────────────────────────────────────────────
if sessions:
    print(f"\n  Per-session node counts:")
    for sid, pts in sorted(sessions.items(), key=lambda x: -len(x[1])):
        domains = list({p.payload.get("domain", p.payload.get("url", "?"))[:30] for p in pts})[:3]
        ts_vals = [p.payload.get("timestamp") or p.payload.get("visited_at") or p.payload.get("created_at") for p in pts]
        ts_vals = [t for t in ts_vals if t]
        time_range = f"{min(ts_vals)} → {max(ts_vals)}" if ts_vals else "no timestamps"
        print(f"\n    session = {str(sid)[:30]}")
        print(f"    nodes   = {len(pts)}")
        print(f"    domains = {domains}")
        print(f"    time    = {time_range}")

# ── 6. Nodes with no session (these cause spider web) ────────────────────────
if no_session:
    print(f"\n{'='*60}")
    print(f"  ⚠️  NODES WITH NO SESSION ID (first 8)")
    print(f"{'='*60}")
    for p in no_session[:8]:
        title = p.payload.get("title", p.payload.get("page_title", "?"))[:50]
        domain = p.payload.get("domain", p.payload.get("url", "?"))[:40]
        print(f"  id={str(p.id)[:12]}  title={title}  domain={domain}")

# ── 7. Sample a full payload so we can see exact field names ──────────────────
print(f"\n{'='*60}")
print(f"  FULL PAYLOAD SAMPLE (first point)")
print(f"{'='*60}")
print(json.dumps(all_points[0].payload, indent=2, default=str))

# ── 8. Diagnosis ──────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print(f"  DIAGNOSIS")
print(f"{'='*60}")

if SESSION_FIELD is None:
    print("  ❌ CAUSE: No session_id field exists in any point.")
    print("     The frontend has nothing to filter on, so it connects everything.")
    print("     FIX: Add session_id to your ingest payload in main.py")

elif len(sessions) == 1:
    print(f"  ⚠️  CAUSE: Only 1 session exists for all {len(all_points)} nodes.")
    print("     Everything is in one giant session → all nodes get connected.")
    print("     FIX: Check your session_id generation logic in main.py.")
    print("          Sessions should rotate after 30+ min of inactivity.")

elif len(no_session) > 0 and len(no_session) == len(all_points):
    print("  ❌ CAUSE: All nodes missing session_id.")
    print("     FIX: session_id is not being saved during ingest.")

elif len(no_session) > 0:
    print(f"  ⚠️  CAUSE: {len(no_session)} nodes have null/missing session_id.")
    print("     These are getting connected to everything in the frontend.")
    print("     FIX: Either backfill their session_ids, or filter them out")
    print("          in the frontend edge-drawing logic (skip null session_id nodes).")

elif len(sessions) > 1:
    print(f"  ✅ Data looks correct — {len(sessions)} distinct sessions found.")
    print("     Spider web is a FRONTEND BUG, not a data bug.")
    print("     The edge-drawing code is not filtering by session_id properly.")
    print("     Look for LineSegments / edge rendering in your Constellation component.")

print(f"{'='*60}\n")
