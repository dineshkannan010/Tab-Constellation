"""
Tab Constellation — Event Processor
=====================================
Reads data/events.jsonl + data/tabs.jsonl to compute:
  - time_spent per tab (from tab_activated / tab_activated gaps)
  - depth per tab (from opener_tab_id chain)
  - tab_closed_without_return (from tab_closed events)

Then updates Qdrant payloads and Neo4j nodes with real values.

Usage:
  python event_processor.py          # process all events
  python event_processor.py --watch  # run every 30s continuously
"""

from __future__ import annotations

import json
import os
import time
import argparse
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
from neo4j import GraphDatabase

load_dotenv()

# ── Config ─────────────────────────────────────────────────────
QDRANT_URL     = "http://localhost:6333"
COLLECTION_NAME = "tab_constellation"
NEO4J_URI      = "bolt://localhost:7687"
NEO4J_USER     = "neo4j"
NEO4J_PASSWORD = os.environ["NEO4J_PASSWORD"]

DATA_DIR    = Path(__file__).parent / "data"
EVENTS_FILE = DATA_DIR / "events.jsonl"
TABS_FILE   = DATA_DIR / "tabs.jsonl"

# ── Helpers ────────────────────────────────────────────────────

def parse_ts(ts: str) -> datetime:
    """Parse ISO timestamp to aware datetime."""
    ts = ts.replace("Z", "+00:00")
    return datetime.fromisoformat(ts)

def url_to_point_id(url: str) -> int:
    return int(hashlib.md5(url.encode()).hexdigest(), 16) % (2**63)

def url_to_node_id(url: str) -> str:
    return f"url_{hashlib.md5(url.encode()).hexdigest()[:12]}"

def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    with path.open("r", encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return records

# ── Core computation ───────────────────────────────────────────

def compute_tab_stats(
    events: list[dict],
    tabs: list[dict],
) -> dict[str, dict]:
    """
    Returns a dict keyed by URL with computed stats:
    {
      url: {
        time_spent: int (seconds),
        depth: int,
        tab_closed_without_return: bool,
        opener_url: str | None,
      }
    }
    """

    # Build tab_id → url map from tabs.jsonl
    tab_url: dict[int, str] = {}
    tab_opener: dict[int, int | None] = {}
    for t in tabs:
        tid = t.get("tab_id")
        url = t.get("url")
        if tid and url and url.startswith("http"):
            tab_url[tid] = url
            tab_opener[tid] = t.get("opener_tab_id")

    # Also update from events (tab_activated carries url sometimes)
    for e in events:
        tid = e.get("tab_id")
        url = e.get("url")
        if tid and url and url.startswith("http") and tid not in tab_url:
            tab_url[tid] = url

    # Sort events by timestamp
    sorted_events = sorted(
        events,
        key=lambda e: parse_ts(e["timestamp"])
    )

    # Track activation times per tab
    # tab_id → last activated timestamp
    active_since: dict[int, datetime] = {}
    # url → total time spent in seconds
    time_spent: dict[str, int] = defaultdict(int)
    # tab_id → set of tab_ids closed without returning
    closed_tabs: set[int] = set()
    # track which tabs were reactivated after close
    returned_tabs: set[int] = set()

    current_active: int | None = None

    for event in sorted_events:
        tab_id    = event.get("tab_id")
        etype     = event.get("event_type")
        ts        = parse_ts(event["timestamp"])

        if etype == "tab_activated":
            # Deactivate previous tab — add time
            if current_active is not None and current_active in active_since:
                elapsed = (ts - active_since[current_active]).total_seconds()
                # Cap at 30 min — avoid overnight idle counting
                elapsed = min(elapsed, 1800)
                if elapsed > 2:  # ignore sub-2s blips
                    url = tab_url.get(current_active)
                    if url:
                        time_spent[url] += int(elapsed)

            # Activate new tab
            active_since[tab_id] = ts
            current_active = tab_id

            # If this tab was previously closed, it returned
            if tab_id in closed_tabs:
                returned_tabs.add(tab_id)

        elif etype == "tab_closed":
            # Add remaining time if this was the active tab
            if tab_id == current_active and tab_id in active_since:
                elapsed = (ts - active_since[tab_id]).total_seconds()
                elapsed = min(elapsed, 1800)
                if elapsed > 2:
                    url = tab_url.get(tab_id)
                    if url:
                        time_spent[url] += int(elapsed)
                current_active = None

            closed_tabs.add(tab_id)
            active_since.pop(tab_id, None)

    # Compute depth from opener chain
    # depth = number of hops from a tab with no opener
    def get_depth(tab_id: int, visited: set | None = None) -> int:
        if visited is None:
            visited = set()
        if tab_id in visited:
            return 0
        visited.add(tab_id)
        opener = tab_opener.get(tab_id)
        if opener is None or opener not in tab_url:
            return 0
        return 1 + get_depth(opener, visited)

    # Build result
    result: dict[str, dict] = {}

    for tab_id, url in tab_url.items():
        if not url.startswith("http"):
            continue
        if "localhost" in url or "127.0.0.1" in url:
            continue

        depth    = get_depth(tab_id)
        closed   = tab_id in closed_tabs
        returned = tab_id in returned_tabs

        existing = result.get(url, {})
        result[url] = {
            "time_spent":               existing.get("time_spent", 0) + time_spent.get(url, 0),
            "depth":                    max(existing.get("depth", 0), depth),
            "tab_closed_without_return": closed and not returned,
            "opener_url":               tab_url.get(tab_opener.get(tab_id)),
        }

    return result

# ── Qdrant updater ─────────────────────────────────────────────

def update_qdrant(stats: dict[str, dict]) -> int:
    client = QdrantClient(url=QDRANT_URL)
    updated = 0

    for url, data in stats.items():
        point_id = url_to_point_id(url)
        try:
            existing = client.retrieve(
                collection_name=COLLECTION_NAME,
                ids=[point_id],
                with_payload=True,
            )
            if not existing:
                continue

            payload = existing[0].payload
            old_time = payload.get("time_spent", 0)
            new_time = max(old_time, data["time_spent"])

            # Recompute focus score with real time
            is_distraction = payload.get("is_distraction", False)
            visit_count    = payload.get("visit_count", 1)
            description    = payload.get("meta_description", "")

            if is_distraction:
                focus = round(max(0.05, 0.2 - visit_count * 0.02), 2)
            else:
                focus = 0.45
                if description:                focus += 0.15
                if new_time > 60:              focus += 0.10
                if new_time > 300:             focus += 0.10
                if new_time > 600:             focus += 0.10
                if visit_count > 1:            focus += 0.10
                focus = min(round(focus, 2), 1.0)

            client.set_payload(
                collection_name=COLLECTION_NAME,
                payload={
                    "time_spent":               new_time,
                    "depth":                    data["depth"],
                    "tab_closed_without_return": data["tab_closed_without_return"],
                    "focus_score":              focus,
                },
                points=[point_id],
            )
            updated += 1

        except Exception as e:
            print(f"  Qdrant update error for {url[:50]}: {e}")

    return updated

# ── Neo4j updater ──────────────────────────────────────────────

def update_neo4j(stats: dict[str, dict]) -> int:
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    updated = 0

    with driver.session() as session:
        for url, data in stats.items():
            node_id = url_to_node_id(url)
            try:
                session.run("""
                    MATCH (n:BrowsingNode {node_id: $node_id})
                    SET n.time_spent = $time_spent,
                        n.depth = $depth,
                        n.tab_closed_without_return = $closed
                """, {
                    "node_id":   node_id,
                    "time_spent": data["time_spent"],
                    "depth":      data["depth"],
                    "closed":     data["tab_closed_without_return"],
                })

                # Create REFERRED_TO edge if opener exists
                if data.get("opener_url"):
                    opener_node_id = url_to_node_id(data["opener_url"])
                    session.run("""
                        MATCH (src:BrowsingNode {node_id: $src_id})
                        MATCH (dst:BrowsingNode {node_id: $dst_id})
                        MERGE (src)-[:REFERRED_TO]->(dst)
                    """, {
                        "src_id": opener_node_id,
                        "dst_id": node_id,
                    })
                updated += 1
            except Exception as e:
                print(f"  Neo4j update error: {e}")

    driver.close()
    return updated

# ── Main ───────────────────────────────────────────────────────

def run_once() -> None:
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Processing events...")

    events = load_jsonl(EVENTS_FILE)
    tabs   = load_jsonl(TABS_FILE)

    print(f"  Loaded {len(events)} events, {len(tabs)} tab records")

    if not events and not tabs:
        print("  No data yet.")
        return

    stats = compute_tab_stats(events, tabs)
    print(f"  Computed stats for {len(stats)} unique URLs")

    # Show top 5 by time spent
    top = sorted(stats.items(), key=lambda x: x[1]["time_spent"], reverse=True)[:5]
    for url, data in top:
        print(f"  {data['time_spent']}s | depth={data['depth']} | "
              f"closed={data['tab_closed_without_return']} | {url[:60]}")

    q_updated = update_qdrant(stats)
    n_updated = update_neo4j(stats)
    print(f"  Updated {q_updated} Qdrant points, {n_updated} Neo4j nodes")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--watch", action="store_true",
                        help="Run continuously every 30 seconds")
    parser.add_argument("--interval", type=int, default=30,
                        help="Watch interval in seconds (default: 30)")
    args = parser.parse_args()

    if args.watch:
        print(f"Watching events every {args.interval}s... (Ctrl+C to stop)")
        while True:
            try:
                run_once()
                time.sleep(args.interval)
            except KeyboardInterrupt:
                print("\nStopped.")
                break
    else:
        run_once()