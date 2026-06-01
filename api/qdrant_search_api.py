"""
Tab Constellation — Qdrant Search API
=======================================
FastAPI routes that expose Qdrant queries as HTTP endpoints.
Your React frontend calls these — not Qdrant directly.

Run standalone (required — Vite proxies /api/* to port 8001):
  uvicorn qdrant_search_api:app --reload --port 8001

Endpoints:
  POST /search/semantic          → find similar nodes by text query
  GET  /features/focus-score     → Focus Score Gauge data
  GET  /features/distraction     → Distraction Fingerprint nodes
  GET  /features/unresolved-loops→ Unresolved Loops list
  GET  /features/guilt-pile      → Guilt Pile list
  GET  /features/dead-stars      → Dead Stars list
  GET  /features/escape-hatches  → Escape Hatch list
  GET  /features/rabbit-hole/{session_id} → Rabbit Hole chain
  GET  /nodes/all                → paginated full node list

  # Insight endpoints — all accept ?hours= time window
  GET  /insights/rabbit-holes          → top rabbit holes (hours window)
  GET  /insights/distraction-summary   → distraction breakdown (hours window)
  GET  /insights/focus-summary         → overall focus stats (hours window)
"""

import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from functools import lru_cache

from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue, Range

from qdrant_config import ACTIVE_CONFIG, EMBEDDING_MODEL_NAME, build_embedding_text

load_dotenv()

NEO4J_URI      = "bolt://localhost:7687"
NEO4J_USER     = "neo4j"
NEO4J_PASSWORD = os.environ["NEO4J_PASSWORD"]


# ─── App setup ─────────────────────────────────────────────────

app = FastAPI(
    title="Tab Constellation — Qdrant API",
    version="1.0.0",
    description="Semantic search and feature queries for Tab Constellation",
)

router = app.router

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # React dev server
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Lazy singletons ───────────────────────────────────────────

@lru_cache(maxsize=1)
def get_qdrant_client() -> QdrantClient:
    cfg = ACTIVE_CONFIG
    if cfg.use_in_memory:
        return QdrantClient(":memory:")
    return QdrantClient(url=cfg.url, api_key=cfg.api_key)


@lru_cache(maxsize=1)
def get_embedding_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(EMBEDDING_MODEL_NAME)


def embed_query(text: str) -> list[float]:
    model = get_embedding_model()
    return model.encode([text], normalize_embeddings=True)[0].tolist()


# ─── Time window helper ────────────────────────────────────────

def hours_to_days(hours: float) -> float:
    """Convert hours to fractional days for days_since_visit filter."""
    return hours / 24.0


def time_filter(hours: Optional[float]) -> Optional[Filter]:
    """
    Return a Qdrant Filter for days_since_visit <= N days.
    If hours is None, returns None (no filter = all time).
    days_since_visit is 0 for tabs visited today (real-time ingestion always sets 0).
    For mock data it's the actual integer days.
    """
    if hours is None:
        return None
    days = hours_to_days(hours)
    return Filter(
        must=[FieldCondition(key="days_since_visit", range=Range(lte=days))]
    )


# ─── Request / Response models ─────────────────────────────────

class SemanticSearchRequest(BaseModel):
    query: str
    top_k: int = 10
    cluster: Optional[str] = None
    exclude_distractions: bool = False
    min_score: float = 0.0


class NodePayload(BaseModel):
    node_id: str
    url: str
    title: str
    domain: str
    cluster: str
    days_since_visit: int
    focus_score: float
    is_distraction: bool
    saved_for_later: bool
    revisited: bool
    tab_closed_without_return: bool
    scroll_depth: float
    depth: int
    session_id: str
    is_escape_node: bool
    time_spent: int
    visit_count: int
    ingested_at: Optional[float] = None
    meta_description: Optional[str] = None
    tab_id: Optional[str] = None
    referrer_url: str = ""


class SemanticSearchResult(BaseModel):
    score: float
    node: NodePayload


class FocusScoreResponse(BaseModel):
    score: float
    distraction_ratio: float
    deep_focus_minutes: int
    top_focus_nodes: list[NodePayload]
    top_distraction_nodes: list[NodePayload]


# ─── Health ────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "collection": ACTIVE_CONFIG.collection_name}


# ─── Semantic search ───────────────────────────────────────────

@app.post("/api/v1/search/semantic", response_model=list[SemanticSearchResult])
def semantic_search(req: SemanticSearchRequest):
    client = get_qdrant_client()
    vector = embed_query(req.query)

    filters = []
    if req.cluster:
        filters.append(FieldCondition(key="cluster", match=MatchValue(value=req.cluster)))
    if req.exclude_distractions:
        filters.append(FieldCondition(key="is_distraction", match=MatchValue(value=False)))
    if req.min_score > 0:
        filters.append(FieldCondition(key="focus_score", range=Range(gte=req.min_score)))

    query_filter = Filter(must=filters) if filters else None

    try:
        results = client.query_points(
            collection_name=ACTIVE_CONFIG.collection_name,
            query=vector,
            query_filter=query_filter,
            limit=req.top_k,
            with_payload=True,
            score_threshold=ACTIVE_CONFIG.score_threshold,
        ).points
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return [
        SemanticSearchResult(score=r.score, node=NodePayload(**r.payload))
        for r in results
    ]


# ─── Feature: Focus Score Gauge ────────────────────────────────

@app.get("/api/v1/features/focus-score", response_model=FocusScoreResponse)
def get_focus_score(days: int = Query(default=7, ge=1, le=90)):
    client = get_qdrant_client()

    all_nodes, _ = client.scroll(
        collection_name=ACTIVE_CONFIG.collection_name,
        scroll_filter=Filter(
            must=[FieldCondition(key="days_since_visit", range=Range(lte=days))]
        ),
        limit=500,
        with_payload=True,
    )
    payloads = [r.payload for r in all_nodes]
    if not payloads:
        raise HTTPException(status_code=404, detail="No nodes found for this time window")

    avg_score = sum(p["focus_score"] for p in payloads) / len(payloads)
    distractions = [p for p in payloads if p["is_distraction"]]
    focus_nodes  = [p for p in payloads if not p["is_distraction"]]
    focus_time   = sum(p["time_spent"] for p in focus_nodes)

    sorted_focus = sorted(focus_nodes,  key=lambda p: p["focus_score"], reverse=True)[:5]
    sorted_dist  = sorted(distractions, key=lambda p: p["time_spent"],  reverse=True)[:5]

    return FocusScoreResponse(
        score=round(avg_score, 3),
        distraction_ratio=round(len(distractions) / len(payloads), 3),
        deep_focus_minutes=round(focus_time / 60),
        top_focus_nodes=[NodePayload(**p) for p in sorted_focus],
        top_distraction_nodes=[NodePayload(**p) for p in sorted_dist],
    )


# ─── Feature: Distraction Fingerprint ─────────────────────────

@app.get("/api/v1/features/distraction")
def get_distraction_fingerprint(limit: int = Query(default=50, le=200)):
    client = get_qdrant_client()
    results, _ = client.scroll(
        collection_name=ACTIVE_CONFIG.collection_name,
        scroll_filter=Filter(
            must=[FieldCondition(key="is_distraction", match=MatchValue(value=True))]
        ),
        limit=limit,
        with_payload=True,
    )
    payloads = [r.payload for r in results]

    domain_map: dict[str, dict] = {}
    for p in payloads:
        d = p["domain"]
        if d not in domain_map:
            domain_map[d] = {"domain": d, "count": 0, "total_time": 0}
        domain_map[d]["count"]      += 1
        domain_map[d]["total_time"] += p["time_spent"]

    return {
        "total_distraction_nodes": len(payloads),
        "by_domain": sorted(domain_map.values(), key=lambda x: x["total_time"], reverse=True),
        "nodes": payloads,
    }


# ─── Feature: Unresolved Loops ─────────────────────────────────

@app.get("/api/v1/features/unresolved-loops")
def get_unresolved_loops(
    max_scroll_depth: float = Query(default=0.9, ge=0.0, le=1.0),
    limit: int = Query(default=50, le=200),
):
    client = get_qdrant_client()
    results, _ = client.scroll(
        collection_name=ACTIVE_CONFIG.collection_name,
        scroll_filter=Filter(
            must=[
                FieldCondition(key="tab_closed_without_return", match=MatchValue(value=True)),
                FieldCondition(key="scroll_depth", range=Range(lt=max_scroll_depth)),
            ]
        ),
        limit=limit,
        with_payload=True,
    )
    payloads = sorted(
        [r.payload for r in results],
        key=lambda p: p["days_since_visit"],
        reverse=True,
    )
    return {"count": len(payloads), "loops": payloads}


# ─── Feature: Guilt Pile ───────────────────────────────────────

@app.get("/api/v1/features/guilt-pile")
def get_guilt_pile(limit: int = Query(default=50, le=200)):
    client = get_qdrant_client()
    results, _ = client.scroll(
        collection_name=ACTIVE_CONFIG.collection_name,
        scroll_filter=Filter(
            must=[
                FieldCondition(key="saved_for_later", match=MatchValue(value=True)),
                FieldCondition(key="revisited",        match=MatchValue(value=False)),
            ]
        ),
        limit=limit,
        with_payload=True,
    )
    payloads = sorted(
        [r.payload for r in results],
        key=lambda p: p["days_since_visit"],
        reverse=True,
    )
    return {"count": len(payloads), "items": payloads}


# ─── Feature: Dead Stars ───────────────────────────────────────

@app.get("/api/v1/features/dead-stars")
def get_dead_stars(
    threshold_days: int = Query(default=21, ge=1),
    limit: int = Query(default=50, le=200),
):
    client = get_qdrant_client()
    results, _ = client.scroll(
        collection_name=ACTIVE_CONFIG.collection_name,
        scroll_filter=Filter(
            must=[
                FieldCondition(key="days_since_visit", range=Range(gte=threshold_days))
            ]
        ),
        limit=limit,
        with_payload=True,
    )
    payloads = sorted(
        [r.payload for r in results],
        key=lambda p: p["days_since_visit"],
        reverse=True,
    )
    return {"count": len(payloads), "dead_stars": payloads}


# ─── Feature: Escape Hatch ─────────────────────────────────────

@app.get("/api/v1/features/escape-hatches")
def get_escape_hatches(limit: int = Query(default=20, le=100)):
    client = get_qdrant_client()
    results, _ = client.scroll(
        collection_name=ACTIVE_CONFIG.collection_name,
        scroll_filter=Filter(
            must=[FieldCondition(key="is_escape_node", match=MatchValue(value=True))]
        ),
        limit=limit,
        with_payload=True,
    )
    return {"count": len(results), "escape_hatches": [r.payload for r in results]}


# ─── Feature: Rabbit Hole ──────────────────────────────────────

@app.get("/api/v1/features/rabbit-hole/{session_id}")
def get_rabbit_hole(session_id: str):
    client = get_qdrant_client()
    results, _ = client.scroll(
        collection_name=ACTIVE_CONFIG.collection_name,
        scroll_filter=Filter(
            must=[FieldCondition(key="session_id", match=MatchValue(value=session_id))]
        ),
        limit=100,
        with_payload=True,
    )
    chain = sorted([r.payload for r in results], key=lambda p: p["depth"])
    if not chain:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")

    max_depth      = max(p["depth"] for p in chain)
    total_time     = sum(p["time_spent"] for p in chain)
    origin_cluster = chain[0]["cluster"] if chain else "unknown"
    exit_cluster   = chain[-1]["cluster"] if chain else "unknown"

    return {
        "session_id":     session_id,
        "max_depth":      max_depth,
        "total_time":     total_time,
        "origin_cluster": origin_cluster,
        "exit_cluster":   exit_cluster,
        "chain":          chain,
    }


# ─── Nodes: paginated full list ────────────────────────────────

@app.get("/api/v1/nodes/all")
def get_all_nodes(
    limit:   int = Query(default=50, le=200),
    offset:  int = Query(default=0, ge=0),
    cluster: Optional[str] = None,
):
    client = get_qdrant_client()
    filters = []
    if cluster:
        filters.append(FieldCondition(key="cluster", match=MatchValue(value=cluster)))

    results, next_offset = client.scroll(
        collection_name=ACTIVE_CONFIG.collection_name,
        scroll_filter=Filter(must=filters) if filters else None,
        limit=limit,
        offset=offset,
        with_payload=True,
        with_vectors=False,
    )
    return {
        "nodes":       [r.payload for r in results],
        "next_offset": next_offset,
        "count":       len(results),
    }


# ─── Chain helper ──────────────────────────────────────────────

def _chain_node(n: dict) -> dict:
    return {
        "title":          n.get("title", ""),
        "domain":         n.get("domain", ""),
        "cluster":        n.get("cluster", ""),
        "depth":          n.get("depth", 0),
        "is_distraction": n.get("is_distraction", False),
        "time_spent":     n.get("time_spent", 0),
        "url":            n.get("url", ""),
    }


# ─── Insight: Rabbit Holes (with time window) ──────────────────

@app.get("/api/v1/insights/rabbit-holes")
def get_rabbit_hole_insights(
    hours: Optional[float] = Query(default=None, ge=1, description="Time window in hours. Omit for all-time.")
):
    """
    Returns top rabbit holes filtered by time window.
    hours=6  → last 6 hours
    hours=24 → last 24 hours
    hours=168 → last 7 days
    Omit hours → all time
    """
    client = get_qdrant_client()

    scroll_filter = time_filter(hours)

    all_results, _ = client.scroll(
        collection_name=ACTIVE_CONFIG.collection_name,
        scroll_filter=scroll_filter,
        limit=500,
        with_payload=True,
    )
    payloads = [r.payload for r in all_results]

    # ── Inter-tab rabbit holes (depth-based) ───────────────────
    inter_tab: list[dict] = []
    sessions: dict[str, list] = {}
    for p in payloads:
        if p.get("depth", 0) >= 2:
            sid = p.get("session_id", "unknown")
            sessions.setdefault(sid, []).append(p)

    for sid, nodes in sessions.items():
        sorted_nodes = sorted(nodes, key=lambda n: n.get("depth", 0))
        inter_tab.append({
            "type":            "new_tab",
            "session_id":      sid,
            "max_depth":       max(n.get("depth", 0) for n in sorted_nodes),
            "total_time":      sum(n.get("time_spent", 0) for n in sorted_nodes),
            "node_count":      len(sorted_nodes),
            "has_distraction": any(n.get("is_distraction") for n in sorted_nodes),
            "origin_cluster":  sorted_nodes[0].get("cluster", "unknown"),
            "exit_cluster":    sorted_nodes[-1].get("cluster", "unknown"),
            "chain":           [_chain_node(n) for n in sorted_nodes],
        })
    inter_tab.sort(key=lambda x: x["max_depth"], reverse=True)

    # ── Same-tab rabbit holes (referrer_url chain + cluster shift) ──
    url_map = {p["url"]: p for p in payloads if p.get("url")}

    children: dict[str, list] = {}
    for p in payloads:
        ref = p.get("referrer_url", "")
        if ref and ref in url_map and ref != p.get("url"):
            children.setdefault(ref, []).append(p)

    roots = [
        url_map[url] for url in url_map
        if url in children
        and (not url_map[url].get("referrer_url") or url_map[url].get("referrer_url") not in url_map)
    ]

    def build_chain(start: dict) -> list[dict]:
        chain, visited, current = [start], {start["url"]}, start["url"]
        while len(chain) < 50:
            nexts = [n for n in children.get(current, []) if n.get("url") not in visited]
            if not nexts:
                break
            nxt = nexts[0]
            chain.append(nxt)
            visited.add(nxt["url"])
            current = nxt["url"]
        return chain

    same_tab: list[dict] = []
    for root in roots:
        chain = build_chain(root)
        if len(chain) < 3:
            continue
        clusters = [n.get("cluster", "") for n in chain]
        shifts = sum(1 for i in range(1, len(clusters)) if clusters[i] != clusters[i - 1])
        if shifts == 0:
            continue
        same_tab.append({
            "type":            "same_tab",
            "session_id":      chain[0].get("session_id", "unknown"),
            "max_depth":       len(chain) - 1,
            "total_time":      sum(n.get("time_spent", 0) for n in chain),
            "node_count":      len(chain),
            "has_distraction": any(n.get("is_distraction") for n in chain),
            "origin_cluster":  clusters[0],
            "exit_cluster":    clusters[-1],
            "chain":           [_chain_node(n) for n in chain],
        })
    same_tab.sort(key=lambda x: x["node_count"], reverse=True)

    return {
        "rabbit_holes": inter_tab[:5] + same_tab[:5],
        "time_window_hours": hours,
    }


# ─── Insight: Distraction Summary (with time window) ──────────

@app.get("/api/v1/insights/distraction-summary")
def get_distraction_summary(
    hours: Optional[float] = Query(default=None, ge=1, description="Time window in hours. Omit for all-time.")
):
    """
    Distraction fingerprint — patterns, domains, time lost.
    Filtered by time window when hours is provided.
    """
    client = get_qdrant_client()

    base_filter = time_filter(hours)

    # Combine distraction=True with optional time filter
    distraction_condition = FieldCondition(key="is_distraction", match=MatchValue(value=True))
    if base_filter:
        scroll_filter = Filter(must=base_filter.must + [distraction_condition])
    else:
        scroll_filter = Filter(must=[distraction_condition])

    results, _ = client.scroll(
        collection_name=ACTIVE_CONFIG.collection_name,
        scroll_filter=scroll_filter,
        limit=200,
        with_payload=True,
    )

    payloads = [r.payload for r in results]
    if not payloads:
        return {
            "total": 0, "time_lost": 0,
            "by_domain": [], "by_cluster": [],
            "time_window_hours": hours,
        }

    total_time = sum(p.get("time_spent", 0) for p in payloads)

    domain_map: dict[str, dict] = {}
    for p in payloads:
        d = p.get("domain", "unknown")
        if d not in domain_map:
            domain_map[d] = {"domain": d, "visits": 0, "time_spent": 0}
        domain_map[d]["visits"]     += p.get("visit_count", 1)
        domain_map[d]["time_spent"] += p.get("time_spent", 0)

    cluster_map: dict[str, dict] = {}
    for p in payloads:
        c = p.get("cluster", "unknown")
        if c not in cluster_map:
            cluster_map[c] = {"cluster": c, "count": 0, "time_spent": 0}
        cluster_map[c]["count"]      += 1
        cluster_map[c]["time_spent"] += p.get("time_spent", 0)

    return {
        "total":              len(payloads),
        "time_lost":          total_time,
        "by_domain":          sorted(domain_map.values(),  key=lambda x: x["time_spent"], reverse=True)[:8],
        "by_cluster":         sorted(cluster_map.values(), key=lambda x: x["time_spent"], reverse=True),
        "time_window_hours":  hours,
    }


# ─── Insight: Focus Summary (with time window) ────────────────

@app.get("/api/v1/insights/focus-summary")
def get_focus_summary(
    hours: Optional[float] = Query(default=None, ge=1, description="Time window in hours. Omit for all-time.")
):
    """
    Overall focus stats for the dashboard.
    Filtered by time window when hours is provided.
    """
    client = get_qdrant_client()

    scroll_filter = time_filter(hours)

    all_nodes, _ = client.scroll(
        collection_name=ACTIVE_CONFIG.collection_name,
        scroll_filter=scroll_filter,
        limit=500,
        with_payload=True,
    )

    payloads = [r.payload for r in all_nodes]
    if not payloads:
        return {
            "avg_focus": 0, "total_time": 0,
            "focus_time": 0, "distraction_time": 0,
            "total_nodes": 0, "distraction_nodes": 0,
            "time_window_hours": hours,
        }

    total_time       = sum(p.get("time_spent", 0) for p in payloads)
    distraction_time = sum(p.get("time_spent", 0) for p in payloads if p.get("is_distraction"))
    focus_time       = total_time - distraction_time
    avg_focus        = sum(p.get("focus_score", 0) for p in payloads) / len(payloads)

    return {
        "avg_focus":          round(avg_focus, 2),
        "total_time":         total_time,
        "focus_time":         focus_time,
        "distraction_time":   distraction_time,
        "total_nodes":        len(payloads),
        "distraction_nodes":  sum(1 for p in payloads if p.get("is_distraction")),
        "time_window_hours":  hours,
    }


# ─── Graph: Referrer Chain (Neo4j) ────────────────────────────

@app.get("/api/v1/graph/referrer-chain/{node_id}")
def get_referrer_chain(node_id: str):
    """
    Trace back how you arrived at a page — pure Neo4j graph traversal.
    """
    try:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USER, NEO4J_PASSWORD)
        )
        with driver.session() as session:
            forward = session.run("""
                MATCH (n:BrowsingNode {node_id: $node_id})-[:REFERRED_TO*1..5]->(m:BrowsingNode)
                RETURN m.title AS title, m.domain AS domain,
                       m.cluster AS cluster, m.node_id AS node_id,
                       m.url AS url
                LIMIT 5
            """, {"node_id": node_id})

            backward = session.run("""
                MATCH (origin:BrowsingNode)-[:REFERRED_TO*1..5]->(target:BrowsingNode {node_id: $node_id})
                RETURN [n IN nodes(
                    shortestPath((origin)-[:REFERRED_TO*]->(target))
                ) | {
                    title: n.title,
                    domain: n.domain,
                    cluster: n.cluster,
                    node_id: n.node_id,
                    url: n.url
                }] AS chain
                ORDER BY length(
                    shortestPath((origin)-[:REFERRED_TO*]->(target))
                ) DESC
                LIMIT 1
            """, {"node_id": node_id})

            forward_chain  = [dict(r) for r in forward]
            backward_row   = backward.single()
            backward_chain = backward_row["chain"] if backward_row else []

        driver.close()
        return {
            "node_id":        node_id,
            "how_i_got_here": backward_chain,
            "led_to":         forward_chain,
        }
    except Exception as e:
        return {"node_id": node_id, "how_i_got_here": [], "led_to": [], "error": str(e)}


# ─── Graph: Full Session Path (Neo4j) ────────────────────────
#
# Given any node_id, walk the FOLLOWED_BY chain to find the
# session root, then traverse forward to get the full ordered
# path for that session. Returns nodes in browsing order so
# the frontend can draw directed arrows A → B → C → D.

@app.get("/api/v1/graph/session-path/{node_id}")
def get_session_path(node_id: str):
    """
    Returns the full ordered FOLLOWED_BY chain for the session
    that contains this node. Neo4j traversal — Qdrant cannot do this.

    Response:
      session_id  : str
      path        : [ { node_id, title, domain, cluster, url, is_distraction } ]
      clicked_idx : int  — index of the clicked node within path
      edge_count  : int  — number of FOLLOWED_BY edges traversed
    """
    try:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USER, NEO4J_PASSWORD)
        )
        with driver.session() as s:
            # Step 1: get session_id for this node
            row = s.run("""
                MATCH (n:BrowsingNode {node_id: $node_id})
                RETURN n.session_id AS session_id
            """, {"node_id": node_id}).single()

            if not row or not row["session_id"]:
                return {"session_id": None, "path": [], "clicked_idx": 0, "edge_count": 0}

            session_id = row["session_id"]

            # Step 2: find the root (no incoming FOLLOWED_BY in this session)
            root_row = s.run("""
                MATCH (n:BrowsingNode {session_id: $session_id})
                WHERE NOT (:BrowsingNode {session_id: $session_id})-[:FOLLOWED_BY]->(n)
                  AND NOT (:BrowsingNode)-[:FOLLOWED_BY]->(n)
                RETURN n.node_id AS root_id
                LIMIT 1
            """, {"session_id": session_id}).single()

            if not root_row:
                # Fallback: get all nodes in session ordered by depth
                results = s.run("""
                    MATCH (n:BrowsingNode {session_id: $session_id})
                    RETURN n.node_id AS node_id, n.title AS title,
                           n.domain AS domain, n.cluster AS cluster,
                           n.url AS url, n.is_distraction AS is_distraction
                    ORDER BY n.depth ASC
                """, {"session_id": session_id})
                path = [dict(r) for r in results]
            else:
                # Step 3: walk FOLLOWED_BY chain from root
                results = s.run("""
                    MATCH path = (root:BrowsingNode {node_id: $root_id})-[:FOLLOWED_BY*0..50]->(n:BrowsingNode)
                    WHERE ALL(x IN nodes(path) WHERE x.session_id = $session_id)
                    WITH n, length(path) AS hop
                    ORDER BY hop ASC
                    RETURN n.node_id AS node_id, n.title AS title,
                           n.domain AS domain, n.cluster AS cluster,
                           n.url AS url, n.is_distraction AS is_distraction
                """, {"root_id": root_row["root_id"], "session_id": session_id})
                path = [dict(r) for r in results]

        driver.close()

        # Find index of clicked node in path
        clicked_idx = next((i for i, n in enumerate(path) if n["node_id"] == node_id), 0)

        return {
            "session_id":  session_id,
            "path":        path,
            "clicked_idx": clicked_idx,
            "edge_count":  max(0, len(path) - 1),
        }

    except Exception as e:
        return {"session_id": None, "path": [], "clicked_idx": 0, "edge_count": 0, "error": str(e)}


# ─── Standalone run ────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("qdrant_search_api:app", host="127.0.0.1", port=8001, reload=True)
