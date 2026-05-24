"""
Tab Constellation — Qdrant Ingestion Pipeline
===============================================
Loads nodes (from mock JSON or real API), generates real 384-dim embeddings
using all-MiniLM-L6-v2, and upserts them into Qdrant with full payloads.

This is the file that runs when you want to push data into Qdrant.

Install:
  pip install qdrant-client sentence-transformers torch

Usage:
  python qdrant_ingestion_pipeline.py                  # ingest mock data
  python qdrant_ingestion_pipeline.py --source api     # ingest from live API
  python qdrant_ingestion_pipeline.py --verify         # run post-ingest checks
"""

import json
import time
import argparse
import hashlib
from pathlib import Path
from typing import Generator

import requests
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    PayloadSchemaType,
    Filter,
    FieldCondition,
    MatchValue,
)

from qdrant_config import (
    ACTIVE_CONFIG,
    EMBEDDING_MODEL_NAME,
    PAYLOAD_INDEXES,
    build_embedding_text,
)

# ─── Paths ─────────────────────────────────────────────────────
MOCK_DATA_PATH = Path(__file__).parent / "mockData.json"
API_NODES_URL  = "http://localhost:8000/nodes"  # teammate 1's endpoint (future)

# ─── Helpers ───────────────────────────────────────────────────

def node_id_to_int(node_id: str) -> int:
    """
    Convert a string node_id ("node_001") to a stable integer Qdrant point ID.
    Uses MD5 hash truncated to 63-bit positive int.
    """
    return int(hashlib.md5(node_id.encode()).hexdigest(), 16) % (2**63)


def load_mock_nodes() -> list[dict]:
    with open(MOCK_DATA_PATH) as f:
        return json.load(f)["nodes"]


def load_api_nodes() -> list[dict]:
    """Pull nodes from teammate 1's FastAPI backend once it's live."""
    resp = requests.get(API_NODES_URL, timeout=10)
    resp.raise_for_status()
    return resp.json()["nodes"]


def node_to_payload(node: dict) -> dict:
    """Map camelCase node fields to snake_case Qdrant payload."""
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


def batch(items: list, size: int) -> Generator[list, None, None]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


# ─── Embedding model ───────────────────────────────────────────

class EmbeddingModel:
    """
    Wrapper around sentence-transformers.
    Lazy-loaded so imports are fast even if not embedding.
    """
    _instance: SentenceTransformer | None = None

    @classmethod
    def get(cls) -> SentenceTransformer:
        if cls._instance is None:
            print(f"Loading embedding model: {EMBEDDING_MODEL_NAME}")
            cls._instance = SentenceTransformer(EMBEDDING_MODEL_NAME)
            print("Model loaded.")
        return cls._instance

    @classmethod
    def embed(cls, texts: list[str]) -> list[list[float]]:
        model = cls.get()
        vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=True)
        return vectors.tolist()


# ─── Collection setup ──────────────────────────────────────────

def ensure_collection(client: QdrantClient, recreate: bool = False) -> None:
    cfg = ACTIVE_CONFIG
    existing = [c.name for c in client.get_collections().collections]

    if cfg.collection_name in existing:
        if recreate:
            client.delete_collection(cfg.collection_name)
            print(f"Deleted existing collection '{cfg.collection_name}'.")
        else:
            print(f"Collection '{cfg.collection_name}' already exists.")
            return

    client.create_collection(
        collection_name=cfg.collection_name,
        vectors_config=VectorParams(
            size=cfg.vector_dim,
            distance=Distance[cfg.distance.upper()],
        ),
    )

    schema_map = {
        "keyword": PayloadSchemaType.KEYWORD,
        "bool":    PayloadSchemaType.BOOL,
        "float":   PayloadSchemaType.FLOAT,
        "integer": PayloadSchemaType.INTEGER,
    }

    for field, schema_type in PAYLOAD_INDEXES.items():
        client.create_payload_index(
            collection_name=cfg.collection_name,
            field_name=field,
            field_schema=schema_map[schema_type],
        )

    print(
        f"Created collection '{cfg.collection_name}' "
        f"(dim={cfg.vector_dim}, distance={cfg.distance}, "
        f"indexes={len(PAYLOAD_INDEXES)})"
    )


# ─── Ingestion ─────────────────────────────────────────────────

def ingest_nodes(client: QdrantClient, nodes: list[dict]) -> None:
    cfg = ACTIVE_CONFIG

    # Build embedding texts
    texts = [
        build_embedding_text(n["title"], n["domain"], n["cluster"])
        for n in nodes
    ]

    print(f"\nGenerating embeddings for {len(nodes)} nodes...")
    t0 = time.time()
    vectors = EmbeddingModel.embed(texts)
    print(f"Embeddings done in {time.time() - t0:.1f}s")

    # Build Qdrant points
    points = [
        PointStruct(
            id=node_id_to_int(node["id"]),
            vector=vector,
            payload=node_to_payload(node),
        )
        for node, vector in zip(nodes, vectors)
    ]

    # Upsert in batches
    print(f"\nUpserting {len(points)} points in batches of {cfg.batch_size}...")
    for i, chunk in enumerate(batch(points, cfg.batch_size)):
        client.upsert(collection_name=cfg.collection_name, points=chunk)
        print(f"  Batch {i + 1}: {len(chunk)} points upserted.")

    total = client.count(cfg.collection_name).count
    print(f"\nIngestion complete. Total points in collection: {total}")


# ─── Post-ingest verification ──────────────────────────────────

def verify_ingestion(client: QdrantClient) -> None:
    cfg = ACTIVE_CONFIG
    print("\n--- Verification ---")

    total = client.count(cfg.collection_name).count
    print(f"Total points: {total}")

    # Check distraction nodes exist
    distraction_count = client.count(
        cfg.collection_name,
        count_filter=Filter(
            must=[FieldCondition(key="is_distraction", match=MatchValue(value=True))]
        ),
    ).count
    print(f"Distraction nodes: {distraction_count}")

    guilt_count = client.count(
        cfg.collection_name,
        count_filter=Filter(
            must=[
                FieldCondition(key="saved_for_later", match=MatchValue(value=True)),
                FieldCondition(key="revisited",        match=MatchValue(value=False)),
            ]
        ),
    ).count
    print(f"Guilt pile nodes: {guilt_count}")

    dead_star_count = client.count(
        cfg.collection_name,
        count_filter=Filter(
            must=[
                FieldCondition(
                    key="days_since_visit",
                    range={"gte": 21},
                )
            ]
        ),
    ).count
    print(f"Dead stars (21+ days): {dead_star_count}")

    # Sample semantic search on first node's freshly generated embedding
    print("\nSample semantic search (query: 'machine learning research arxiv'):")
    query_vec = EmbeddingModel.embed(["machine learning research arxiv"])[0]
    results = client.query_points(
        collection_name=cfg.collection_name,
        query=query_vec,
        limit=5,
        with_payload=True,
    ).points
    for r in results:
        print(f"  [{r.score:.3f}] {r.payload['title']}")


# ─── Entry point ───────────────────────────────────────────────

def get_client() -> QdrantClient:
    cfg = ACTIVE_CONFIG
    if cfg.use_in_memory:
        return QdrantClient(":memory:")
    return QdrantClient(url=cfg.url, api_key=cfg.api_key)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        choices=["mock", "api"],
        default="mock",
        help="Data source: 'mock' (mockData.json) or 'api' (live backend)",
    )
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Delete and recreate the collection before ingesting",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Run post-ingestion verification checks",
    )
    args = parser.parse_args()

    client = get_client()
    ensure_collection(client, recreate=args.recreate)

    nodes = load_mock_nodes() if args.source == "mock" else load_api_nodes()
    print(f"Loaded {len(nodes)} nodes from source: {args.source}")

    ingest_nodes(client, nodes)

    if args.verify:
        verify_ingestion(client)
