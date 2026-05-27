"""
Tab Constellation — Qdrant Search API
=======================================
FastAPI routes that expose Qdrant queries as HTTP endpoints.
Your React frontend calls these — not Qdrant directly.

Mount this router inside teammate 1's main FastAPI app:
  from qdrant_search_api import router as qdrant_router
  app.include_router(qdrant_router, prefix="/api/v1")

Or run standalone for testing:
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
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from functools import lru_cache

from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue, Range

from qdrant_config import ACTIVE_CONFIG, EMBEDDING_MODEL_NAME, build_embedding_text


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
        # In-memory client loses data on restart — for dev only.
        # Switch to url= for persistent local server.
        return QdrantClient(":memory:")
    return QdrantClient(url=cfg.url, api_key=cfg.api_key)


@lru_cache(maxsize=1)
def get_embedding_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(EMBEDDING_MODEL_NAME)


def embed_query(text: str) -> list[float]:
    model = get_embedding_model()
    return model.encode([text], normalize_embeddings=True)[0].tolist()


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


class SemanticSearchResult(BaseModel):
    score: float
    node: NodePayload


class FocusScoreResponse(BaseModel):
    score: float                        # 0–1 average focus score
    distraction_ratio: float            # % of nodes that are distractions
    deep_focus_minutes: int             # total non-distraction time in minutes
    top_focus_nodes: list[NodePayload]  # highest focus score nodes
    top_distraction_nodes: list[NodePayload]


# ─── Health ────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "collection": ACTIVE_CONFIG.collection_name}


# ─── Semantic search ───────────────────────────────────────────

@app.post("/api/v1/search/semantic", response_model=list[SemanticSearchResult])
def semantic_search(req: SemanticSearchRequest):
    """
    Embed a text query and return the most similar nodes.
    Used by: Three.js constellation (hover preview), search bar.
    """
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
    """
    Aggregate focus stats for the last N days.
    Used by: Focus Score Gauge widget.
    """
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

    sorted_focus  = sorted(focus_nodes,  key=lambda p: p["focus_score"], reverse=True)[:5]
    sorted_dist   = sorted(distractions, key=lambda p: p["time_spent"],  reverse=True)[:5]

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
    """
    All distraction nodes with domain and cluster breakdowns.
    Used by: Distraction Fingerprint chart.
    """
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

    # Aggregate by domain
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
    """
    Pages closed before being read, ordered by staleness.
    Used by: Unresolved Loops list.
    """
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
    """
    Saved-for-later nodes never revisited, ordered by staleness.
    Used by: Guilt Pile feature.
    """
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
    """
    Nodes not visited for threshold_days or more.
    Used by: Dead Stars — dim nodes in the constellation.
    """
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
    """
    Nodes that broke focus sessions.
    Used by: Escape Hatch feature.
    """
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
    """
    Full node chain for a session, ordered by depth.
    Used by: Rabbit Hole path visualization in Three.js.
    """
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

    max_depth = max(p["depth"] for p in chain)
    total_time = sum(p["time_spent"] for p in chain)
    origin_cluster = chain[0]["cluster"] if chain else "unknown"
    exit_cluster   = chain[-1]["cluster"] if chain else "unknown"

    return {
        "session_id":      session_id,
        "max_depth":       max_depth,
        "total_time":      total_time,
        "origin_cluster":  origin_cluster,
        "exit_cluster":    exit_cluster,
        "chain":           chain,
    }


# ─── Nodes: paginated full list ────────────────────────────────

@app.get("/api/v1/nodes/all")
def get_all_nodes(
    limit:  int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    cluster: Optional[str] = None,
):
    """
    Paginated list of all nodes, optionally filtered by cluster.
    Used by: Three.js initial constellation load.
    """
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


@app.get("/api/v1/insights/rabbit-holes")
def get_rabbit_hole_insights():
    """
    Find sessions with depth > 2 — the actual rabbit holes.
    Returns sessions ordered by max depth descending.
    """
    client = get_qdrant_client()
    results, _ = client.scroll(
        collection_name=ACTIVE_CONFIG.collection_name,
        scroll_filter=Filter(
            must=[FieldCondition(key="depth", range=Range(gte=2))]
        ),
        limit=200,
        with_payload=True,
    )
    
    # Group by session
    sessions: dict[str, list] = {}
    for r in results:
        p = r.payload
        sid = p.get("session_id", "unknown")
        if sid not in sessions:
            sessions[sid] = []
        sessions[sid].append(p)
    
    # Build rabbit hole chains ordered by depth
    rabbit_holes = []
    for sid, nodes in sessions.items():
        sorted_nodes = sorted(nodes, key=lambda n: n.get("depth", 0))
        max_depth = max(n.get("depth", 0) for n in sorted_nodes)
        total_time = sum(n.get("time_spent", 0) for n in sorted_nodes)
        has_distraction = any(n.get("is_distraction") for n in sorted_nodes)
        
        rabbit_holes.append({
            "session_id":       sid,
            "max_depth":        max_depth,
            "total_time":       total_time,
            "node_count":       len(sorted_nodes),
            "has_distraction":  has_distraction,
            "origin_cluster":   sorted_nodes[0].get("cluster", "unknown"),
            "exit_cluster":     sorted_nodes[-1].get("cluster", "unknown"),
            "chain": [{
                "title":        n.get("title", ""),
                "domain":       n.get("domain", ""),
                "cluster":      n.get("cluster", ""),
                "depth":        n.get("depth", 0),
                "is_distraction": n.get("is_distraction", False),
                "time_spent":   n.get("time_spent", 0),
                "url":          n.get("url", ""),
            } for n in sorted_nodes],
        })
    
    rabbit_holes.sort(key=lambda x: x["max_depth"], reverse=True)
    return {"rabbit_holes": rabbit_holes[:10]}


@app.get("/api/v1/insights/distraction-summary")
def get_distraction_summary():
    """
    Distraction fingerprint — patterns, domains, time lost.
    """
    client = get_qdrant_client()
    results, _ = client.scroll(
        collection_name=ACTIVE_CONFIG.collection_name,
        scroll_filter=Filter(
            must=[FieldCondition(key="is_distraction", match=MatchValue(value=True))]
        ),
        limit=200,
        with_payload=True,
    )
    
    payloads = [r.payload for r in results]
    if not payloads:
        return {"total": 0, "time_lost": 0, "by_domain": [], "by_cluster": []}
    
    total_time = sum(p.get("time_spent", 0) for p in payloads)
    
    # By domain
    domain_map: dict[str, dict] = {}
    for p in payloads:
        d = p.get("domain", "unknown")
        if d not in domain_map:
            domain_map[d] = {"domain": d, "visits": 0, "time_spent": 0}
        domain_map[d]["visits"]     += p.get("visit_count", 1)
        domain_map[d]["time_spent"] += p.get("time_spent", 0)
    
    # By cluster
    cluster_map: dict[str, dict] = {}
    for p in payloads:
        c = p.get("cluster", "unknown")
        if c not in cluster_map:
            cluster_map[c] = {"cluster": c, "count": 0, "time_spent": 0}
        cluster_map[c]["count"]      += 1
        cluster_map[c]["time_spent"] += p.get("time_spent", 0)
    
    return {
        "total":      len(payloads),
        "time_lost":  total_time,
        "by_domain":  sorted(domain_map.values(),  key=lambda x: x["time_spent"], reverse=True)[:8],
        "by_cluster": sorted(cluster_map.values(), key=lambda x: x["time_spent"], reverse=True),
    }


@app.get("/api/v1/insights/focus-summary")  
def get_focus_summary():
    """Overall focus stats for the dashboard."""
    client = get_qdrant_client()
    all_nodes, _ = client.scroll(
        collection_name=ACTIVE_CONFIG.collection_name,
        limit=500,
        with_payload=True,
    )
    
    payloads = [r.payload for r in all_nodes]
    if not payloads:
        return {"avg_focus": 0, "total_time": 0, "focus_time": 0, "distraction_time": 0}
    
    total_time      = sum(p.get("time_spent", 0) for p in payloads)
    distraction_time = sum(p.get("time_spent", 0) for p in payloads if p.get("is_distraction"))
    focus_time      = total_time - distraction_time
    avg_focus       = sum(p.get("focus_score", 0) for p in payloads) / len(payloads)
    
    return {
        "avg_focus":         round(avg_focus, 2),
        "total_time":        total_time,
        "focus_time":        focus_time,
        "distraction_time":  distraction_time,
        "total_nodes":       len(payloads),
        "distraction_nodes": sum(1 for p in payloads if p.get("is_distraction")),
    }


# ─── Standalone run ────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("qdrant_search_api:app", host="0.0.0.0", port=8001, reload=True)
