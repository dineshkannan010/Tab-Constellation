"""
Tab Constellation — Qdrant Store
=================================
Collection schema, indexing, and search/retrieval utilities.
Run this file directly to bootstrap the collection from mockData.json.

Install:
  pip install qdrant-client sentence-transformers

Usage:
  python qdrant_store.py               # bootstrap collection from mock data
  python qdrant_store.py --search      # run a sample semantic search
"""

import json
import argparse
from pathlib import Path
from typing import Optional
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    Range,
    MatchValue,
    PayloadSchemaType,
)

# ─── Config ────────────────────────────────────────────────────

COLLECTION_NAME = "tab_constellation"

# Embedding dimensions.
# If using a real embedding model (e.g. all-MiniLM-L6-v2) this is 384.
# Mock data uses 10-dim vectors for simplicity — change to 384 when real.
VECTOR_DIM = 10

# Qdrant connection — local in-memory for dev, swap URL for cloud
QDRANT_URL = "http://localhost:6333"  # or ":memory:" for pure in-memory
USE_IN_MEMORY = True                  # flip to False when running a real server

MOCK_DATA_PATH = Path(__file__).parent / "mockData.json"

# ─── Client factory ────────────────────────────────────────────

def get_client() -> QdrantClient:
    if USE_IN_MEMORY:
        return QdrantClient(":memory:")
    return QdrantClient(url=QDRANT_URL)


# ─── Collection setup ──────────────────────────────────────────

def create_collection(client: QdrantClient) -> None:
    """
    Create the Qdrant collection with:
      - Cosine distance (best for semantic similarity of text embeddings)
      - Payload indexes for every field used in feature filters

    Schema rationale:
      - cluster        → keyword index  (filter by topic cluster)
      - is_distraction → bool index     (Distraction Fingerprint filter)
      - saved_for_later→ bool index     (Guilt Pile filter)
      - tab_closed_without_return → bool (Unresolved Loops filter)
      - is_escape_node → bool           (Escape Hatch filter)
      - days_since_visit → float/int    (Dead Stars range filter)
      - session_id     → keyword        (Rabbit Hole session grouping)
      - depth          → int            (Rabbit Hole depth filter)
      - focus_score    → float          (Focus Gauge range filter)
      - domain         → keyword        (per-domain filtering/analytics)
    """
    existing = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME in existing:
        print(f"Collection '{COLLECTION_NAME}' already exists — skipping creation.")
        return

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(
            size=VECTOR_DIM,
            distance=Distance.COSINE,
        ),
    )

    # Payload indexes — critical for fast filtering in feature queries
    payload_indexes = {
        "cluster":                  PayloadSchemaType.KEYWORD,
        "domain":                   PayloadSchemaType.KEYWORD,
        "session_id":               PayloadSchemaType.KEYWORD,
        "is_distraction":           PayloadSchemaType.BOOL,
        "saved_for_later":          PayloadSchemaType.BOOL,
        "tab_closed_without_return":PayloadSchemaType.BOOL,
        "is_escape_node":           PayloadSchemaType.BOOL,
        "revisited":                PayloadSchemaType.BOOL,
        "days_since_visit":         PayloadSchemaType.FLOAT,
        "focus_score":              PayloadSchemaType.FLOAT,
        "scroll_depth":             PayloadSchemaType.FLOAT,
        "depth":                    PayloadSchemaType.INTEGER,
        "visit_count":              PayloadSchemaType.INTEGER,
        "time_spent":               PayloadSchemaType.INTEGER,
    }

    for field, schema_type in payload_indexes.items():
        client.create_payload_index(
            collection_name=COLLECTION_NAME,
            field_name=field,
            field_schema=schema_type,
        )

    print(f"Collection '{COLLECTION_NAME}' created with {len(payload_indexes)} payload indexes.")


# ─── Indexing ──────────────────────────────────────────────────

def node_to_payload(node: dict) -> dict:
    """
    Flatten a ConstellationNode into a Qdrant payload.
    Keep keys snake_case to match QdrantPayload TypeScript type.
    """
    return {
        "node_id":                   node["id"],
        "url":                       node["url"],
        "title":                     node["title"],
        "domain":                    node["domain"],
        "visited_at":                node["visitedAt"],
        "last_visited_at":           node["lastVisitedAt"],
        "days_since_visit":          node["daysSinceVisit"],
        "visit_count":               node["visitCount"],
        "time_spent":                node["timeSpent"],
        "scroll_depth":              node["scrollDepth"],
        "tab_closed_without_return": node["tabClosedWithoutReturn"],
        "referrer":                  node.get("referrer"),
        "depth":                     node["depth"],
        "session_id":                node["sessionId"],
        "cluster":                   node["cluster"],
        "is_distraction":            node["isDistraction"],
        "focus_score":               node["focusScore"],
        "saved_for_later":           node["savedForLater"],
        "revisited":                 node["revisited"],
        "is_escape_node":            node["isEscapeNode"],
    }


def index_nodes(client: QdrantClient, nodes: list[dict]) -> None:
    """
    Upsert all nodes into Qdrant.
    Uses a sequential integer ID derived from the node_id string.
    """
    points = []
    for i, node in enumerate(nodes):
        points.append(
            PointStruct(
                id=i + 1,  # Qdrant requires integer or UUID IDs
                vector=node["embedding"],
                payload=node_to_payload(node),
            )
        )

    client.upsert(collection_name=COLLECTION_NAME, points=points)
    print(f"Indexed {len(points)} nodes into '{COLLECTION_NAME}'.")


# ─── Search & Retrieval ────────────────────────────────────────

def semantic_search(
    client: QdrantClient,
    query_vector: list[float],
    top_k: int = 10,
    cluster: Optional[str] = None,
) -> list[dict]:
    """
    Find the top-k semantically similar nodes.
    Optionally filter by cluster.

    Used by: constellation rendering (find neighbours), Rabbit Hole (find similar hops)
    """
    query_filter = None
    if cluster:
        query_filter = Filter(
            must=[FieldCondition(key="cluster", match=MatchValue(value=cluster))]
        )

    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        query_filter=query_filter,
        limit=top_k,
        with_payload=True,
    ).points
    return [{"score": r.score, "payload": r.payload} for r in results]


def get_distraction_nodes(
    client: QdrantClient,
    limit: int = 50,
) -> list[dict]:
    """
    Retrieve all distraction nodes, sorted by focus_score ascending.
    Used by: Distraction Fingerprint feature.
    """
    results, _ = client.scroll(
        collection_name=COLLECTION_NAME,
        scroll_filter=Filter(
            must=[FieldCondition(key="is_distraction", match=MatchValue(value=True))]
        ),
        limit=limit,
        with_payload=True,
    )
    return [r.payload for r in results]


def get_unresolved_loops(
    client: QdrantClient,
    max_scroll_depth: float = 0.9,
    limit: int = 50,
) -> list[dict]:
    """
    Nodes closed without returning and not fully read.
    Used by: Unresolved Loops feature.
    """
    results, _ = client.scroll(
        collection_name=COLLECTION_NAME,
        scroll_filter=Filter(
            must=[
                FieldCondition(
                    key="tab_closed_without_return",
                    match=MatchValue(value=True),
                ),
                FieldCondition(
                    key="scroll_depth",
                    range=Range(lt=max_scroll_depth),
                ),
            ]
        ),
        limit=limit,
        with_payload=True,
    )
    return sorted(
        [r.payload for r in results],
        key=lambda p: p["days_since_visit"],
        reverse=True,
    )


def get_guilt_pile(
    client: QdrantClient,
    limit: int = 50,
) -> list[dict]:
    """
    Saved-for-later nodes never revisited.
    Used by: Guilt Pile feature.
    """
    results, _ = client.scroll(
        collection_name=COLLECTION_NAME,
        scroll_filter=Filter(
            must=[
                FieldCondition(key="saved_for_later", match=MatchValue(value=True)),
                FieldCondition(key="revisited", match=MatchValue(value=False)),
            ]
        ),
        limit=limit,
        with_payload=True,
    )
    return sorted(
        [r.payload for r in results],
        key=lambda p: p["days_since_visit"],
        reverse=True,
    )


def get_dead_stars(
    client: QdrantClient,
    threshold_days: int = 21,
    limit: int = 50,
) -> list[dict]:
    """
    Nodes not visited for threshold_days or more.
    Used by: Dead Stars feature.
    """
    results, _ = client.scroll(
        collection_name=COLLECTION_NAME,
        scroll_filter=Filter(
            must=[
                FieldCondition(
                    key="days_since_visit",
                    range=Range(gte=threshold_days),
                )
            ]
        ),
        limit=limit,
        with_payload=True,
    )
    return sorted(
        [r.payload for r in results],
        key=lambda p: p["days_since_visit"],
        reverse=True,
    )


def get_escape_hatches(
    client: QdrantClient,
    limit: int = 20,
) -> list[dict]:
    """
    Escape nodes — first distraction after a focus session.
    Used by: Escape Hatch feature.
    """
    results, _ = client.scroll(
        collection_name=COLLECTION_NAME,
        scroll_filter=Filter(
            must=[FieldCondition(key="is_escape_node", match=MatchValue(value=True))]
        ),
        limit=limit,
        with_payload=True,
    )
    return [r.payload for r in results]


def get_rabbit_holes(
    client: QdrantClient,
    session_id: str,
) -> list[dict]:
    """
    All nodes in a session, ordered by depth — reconstructs the rabbit hole chain.
    Used by: Rabbit Hole feature.
    """
    results, _ = client.scroll(
        collection_name=COLLECTION_NAME,
        scroll_filter=Filter(
            must=[
                FieldCondition(key="session_id", match=MatchValue(value=session_id))
            ]
        ),
        limit=100,
        with_payload=True,
    )
    return sorted([r.payload for r in results], key=lambda p: p["depth"])


def get_focus_score_nodes(
    client: QdrantClient,
    min_score: float = 0.0,
    max_score: float = 1.0,
    limit: int = 50,
) -> list[dict]:
    """
    Retrieve nodes within a focus_score range.
    Used by: Focus Score Gauge drill-down.
    """
    results, _ = client.scroll(
        collection_name=COLLECTION_NAME,
        scroll_filter=Filter(
            must=[
                FieldCondition(
                    key="focus_score",
                    range=Range(gte=min_score, lte=max_score),
                )
            ]
        ),
        limit=limit,
        with_payload=True,
    )
    return [r.payload for r in results]


# ─── Bootstrap (run directly) ──────────────────────────────────

def bootstrap_from_mock(client: QdrantClient) -> None:
    with open(MOCK_DATA_PATH, "r") as f:
        data = json.load(f)

    create_collection(client)
    index_nodes(client, data["nodes"])
    print(f"Bootstrap complete. Total points: {client.count(COLLECTION_NAME).count}")


def demo_searches(client: QdrantClient) -> None:
    print("\n--- Demo: Unresolved Loops ---")
    loops = get_unresolved_loops(client)
    for item in loops[:5]:
        print(f"  [{item['days_since_visit']}d] {item['title']} (scroll: {item['scroll_depth']:.0%})")

    print("\n--- Demo: Guilt Pile ---")
    guilt = get_guilt_pile(client)
    for item in guilt[:5]:
        print(f"  [{item['days_since_visit']}d] {item['title']}")

    print("\n--- Demo: Dead Stars (21+ days) ---")
    dead = get_dead_stars(client, threshold_days=21)
    for item in dead[:5]:
        print(f"  [{item['days_since_visit']}d] {item['title']}")

    print("\n--- Demo: Escape Hatches ---")
    escape = get_escape_hatches(client)
    for item in escape[:5]:
        print(f"  {item['title']} (session: {item['session_id']})")

    print("\n--- Demo: Semantic search (query = first node's embedding) ---")
    with open(MOCK_DATA_PATH) as f:
        data = json.load(f)
    query_vec = data["nodes"][0]["embedding"]
    hits = semantic_search(client, query_vec, top_k=5)
    for h in hits:
        print(f"  [{h['score']:.3f}] {h['payload']['title']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--search", action="store_true", help="Run demo searches after bootstrap")
    args = parser.parse_args()

    client = get_client()
    bootstrap_from_mock(client)

    if args.search:
        demo_searches(client)
