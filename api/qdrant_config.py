# ============================================================
# Tab Constellation — Qdrant Config
# Single source of truth for all Qdrant settings.
# Import this everywhere instead of hardcoding values.
# ============================================================

from dataclasses import dataclass
from enum import Enum


class Environment(str, Enum):
    DEVELOPMENT = "development"
    PRODUCTION  = "production"


@dataclass(frozen=True)
class QdrantConfig:
    # Connection
    url:             str
    use_in_memory:   bool
    api_key:         str | None

    # Collection
    collection_name: str
    vector_dim:      int        # 384 for all-MiniLM-L6-v2
    distance:        str        # "Cosine" | "Dot" | "Euclid"

    # Search defaults
    default_top_k:   int
    score_threshold: float      # minimum similarity score to return a result

    # Ingestion
    batch_size:      int        # how many nodes to upsert per batch


# ── Development (in-memory, no server needed) ────────────────
DEV_CONFIG = QdrantConfig(
    url              = ":memory:",
    use_in_memory    = True,
    api_key          = None,
    collection_name  = "tab_constellation",
    vector_dim       = 384,
    distance         = "Cosine",
    default_top_k    = 10,
    score_threshold  = 0.55,
    batch_size       = 50,
)

# ── Production (local Docker or Qdrant Cloud) ────────────────
PROD_CONFIG = QdrantConfig(
    url              = "http://localhost:6333",  # swap for Qdrant Cloud URL
    use_in_memory    = False,
    api_key          = None,                     # set for Qdrant Cloud
    collection_name  = "tab_constellation",
    vector_dim       = 384,
    distance         = "Cosine",
    default_top_k    = 10,
    score_threshold  = 0.15,
    batch_size       = 100,
)

# ── Active config ─────────────────────────────────────────────
# Change ENVIRONMENT to switch between dev and prod.
ENVIRONMENT   = Environment.PRODUCTION
ACTIVE_CONFIG = DEV_CONFIG if ENVIRONMENT == Environment.DEVELOPMENT else PROD_CONFIG

# ── Embedding model ───────────────────────────────────────────
EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

# Text template used to generate each node's embedding.
# Combines the most semantically rich fields into one sentence.
# Format: "{title} on {domain} about {cluster}"
def build_embedding_text(title: str, domain: str, cluster: str) -> str:
    return f"{title} on {domain} about {cluster}"


# ── Payload index definitions (reused by store + tests) ──────
PAYLOAD_INDEXES: dict[str, str] = {
    "cluster":                   "keyword",
    "domain":                    "keyword",
    "session_id":                "keyword",
    "is_distraction":            "bool",
    "saved_for_later":           "bool",
    "tab_closed_without_return": "bool",
    "is_escape_node":            "bool",
    "revisited":                 "bool",
    "days_since_visit":          "float",
    "focus_score":               "float",
    "scroll_depth":              "float",
    "depth":                     "integer",
    "visit_count":               "integer",
    "time_spent":                "integer",
}
