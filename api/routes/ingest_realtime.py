"""
Tab Constellation — Real-time ingestion into Qdrant + Neo4j.
4-layer classification + content-aware distraction detection.
"""

from __future__ import annotations
import hashlib
from functools import lru_cache
from neo4j import GraphDatabase
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, PayloadSchemaType

# ── Config ─────────────────────────────────────────────────────
QDRANT_URL      = "http://localhost:6333"
COLLECTION_NAME = "tab_constellation"
VECTOR_DIM      = 384
NEO4J_URI       = "bolt://localhost:7687"
NEO4J_USER      = "neo4j"
NEO4J_PASSWORD  = "constellation"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
NLI_MODEL       = "cross-encoder/nli-MiniLM2-L6-H768"

# ── Universal clusters ─────────────────────────────────────────
CLUSTER_NAMES = [
    "research", "work", "entertainment", "shopping",
    "social", "news", "health", "finance",
    "travel", "creative", "reference", "communication",
]

# ── Layer 1: Definitive domain map ─────────────────────────────
DEFINITIVE_DOMAINS: dict[str, str] = {
    # Entertainment — always
    "netflix.com": "entertainment", "twitch.tv": "entertainment",
    "tiktok.com": "entertainment", "spotify.com": "entertainment",
    "imdb.com": "entertainment", "primevideo.com": "entertainment",
    "disneyplus.com": "entertainment", "hulu.com": "entertainment",
    "soundcloud.com": "entertainment", "9gag.com": "entertainment",
    "buzzfeed.com": "entertainment",

    # Social — may override to research based on content
    "twitter.com": "social", "x.com": "social",
    "instagram.com": "social", "facebook.com": "social",
    "linkedin.com": "social", "threads.net": "social",
    "pinterest.com": "social", "snapchat.com": "social",
    # reddit handled separately — content-aware

    # Reference — encyclopedic content
    "en.wikipedia.org": "reference", "wikipedia.org": "reference",
    "stackoverflow.com": "reference", "stackexchange.com": "reference",
    "developer.mozilla.org": "reference", "docs.python.org": "reference",
    "kubernetes.io": "reference", "docs.docker.com": "reference",
    "devdocs.io": "reference", "man7.org": "reference",
    "w3schools.com": "reference",

    # Research
    "arxiv.org": "research", "huggingface.co": "research",
    "paperswithcode.com": "research", "semanticscholar.org": "research",
    "pubmed.ncbi.nlm.nih.gov": "research", "researchgate.net": "research",
    "openai.com": "research", "anthropic.com": "research",
    "deepmind.google": "research", "mistral.ai": "research",
    "qdrant.tech": "research",

    # Work / Code
    "github.com": "work", "gitlab.com": "work",
    "bitbucket.org": "work", "jira.atlassian.com": "work",
    "notion.so": "work", "trello.com": "work",
    "asana.com": "work", "clickup.com": "work",
    "linear.app": "work", "vllm.ai": "work",
    "pytorch.org": "research", "tensorflow.org": "research",

    # News
    "bbc.com": "news", "bbc.co.uk": "news",
    "cnn.com": "news", "reuters.com": "news",
    "theguardian.com": "news", "nytimes.com": "news",
    "techcrunch.com": "news", "theverge.com": "news",
    "wired.com": "news", "arstechnica.com": "news",
    "news.ycombinator.com": "news",

    # Finance
    "bloomberg.com": "finance", "investopedia.com": "finance",
    "tradingview.com": "finance", "coinbase.com": "finance",
    "binance.com": "finance", "robinhood.com": "finance",

    # Shopping
    "amazon.com": "shopping", "ebay.com": "shopping",
    "etsy.com": "shopping", "walmart.com": "shopping",

    # Travel
    "airbnb.com": "travel", "booking.com": "travel",
    "tripadvisor.com": "travel", "skyscanner.com": "travel",

    # Health
    "webmd.com": "health", "mayoclinic.org": "health",
    "healthline.com": "health",

    # Creative
    "figma.com": "creative", "canva.com": "creative",
    "behance.net": "creative", "dribbble.com": "creative",
    "framer.com": "creative",

    # Communication
    "mail.google.com": "communication",
    "outlook.live.com": "communication",
    "slack.com": "communication", "zoom.us": "communication",
    "teams.microsoft.com": "communication",
    "calendar.google.com": "communication",

    # Learning
    "coursera.org": "research", "udemy.com": "research",
    "khanacademy.org": "research", "edx.org": "research",
    "freecodecamp.org": "work", "brilliant.org": "research",
}

# ── Content signals ────────────────────────────────────────────
FOCUS_SIGNALS = [
    "tutorial", "documentation", "how to", "guide", "learn",
    "explained", "introduction to", "deep dive", "analysis",
    "research", "paper", "study", "course", "lecture",
    "implementation", "algorithm", "architecture", "technical",
    "code", "programming", "engineering", "science", "math",
    "review", "breakdown", "walkthrough", "best practices",
    "open source", "library", "framework", "api", "database",
]

SHALLOW_SIGNALS = [
    "feed", "home", "trending", "explore", "timeline",
    "for you", "recommended", "watch later", "subscriptions",
    "notifications", "messages", "stories",
]

# ── Always distraction domains ─────────────────────────────────
ALWAYS_DISTRACTION = {
    "netflix.com", "tiktok.com", "twitch.tv",
    "9gag.com", "buzzfeed.com", "instagram.com",
}

# ── Social domains — content-aware ────────────────────────────
SOCIAL_DOMAINS = {
    "reddit.com", "old.reddit.com", "twitter.com", "x.com",
    "facebook.com", "linkedin.com", "threads.net",
}

# ── Singletons ─────────────────────────────────────────────────

@lru_cache(maxsize=1)
def get_qdrant() -> QdrantClient:
    client = QdrantClient(url=QDRANT_URL)
    _ensure_collection(client)
    return client

@lru_cache(maxsize=1)
def get_neo4j():
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

@lru_cache(maxsize=1)
def get_embedding_model():
    from sentence_transformers import SentenceTransformer
    print("Loading embedding model...")
    m = SentenceTransformer(EMBEDDING_MODEL)
    print("Embedding model ready.")
    return m

@lru_cache(maxsize=1)
def get_classifier():
    from transformers import pipeline as hf_pipeline
    print("Loading NLI classifier...")
    clf = hf_pipeline(
        "zero-shot-classification",
        model=NLI_MODEL,
        device=-1,
    )
    print("NLI classifier ready.")
    return clf

def _ensure_collection(client: QdrantClient) -> None:
    names = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME in names:
        return
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
    )
    for field, ftype in [
        ("domain",                    PayloadSchemaType.KEYWORD),
        ("session_id",                PayloadSchemaType.KEYWORD),
        ("cluster",                   PayloadSchemaType.KEYWORD),
        ("is_distraction",            PayloadSchemaType.BOOL),
        ("saved_for_later",           PayloadSchemaType.BOOL),
        ("tab_closed_without_return", PayloadSchemaType.BOOL),
        ("is_escape_node",            PayloadSchemaType.BOOL),
        ("revisited",                 PayloadSchemaType.BOOL),
        ("days_since_visit",          PayloadSchemaType.FLOAT),
        ("focus_score",               PayloadSchemaType.FLOAT),
        ("scroll_depth",              PayloadSchemaType.FLOAT),
        ("depth",                     PayloadSchemaType.INTEGER),
        ("visit_count",               PayloadSchemaType.INTEGER),
        ("time_spent",                PayloadSchemaType.INTEGER),
    ]:
        client.create_payload_index(COLLECTION_NAME, field, ftype)
    print(f"Collection '{COLLECTION_NAME}' created.")

# ── Helpers ────────────────────────────────────────────────────

def _normalize_domain(domain: str) -> str:
    d = domain.lower()
    return d[4:] if d.startswith("www.") else d

def _classify_cluster(
    title: str,
    domain: str,
    description: str = "",
    dom_snippet: str = "",
) -> str:
    d = _normalize_domain(domain)
    t = title.lower()

    # Layer 1: definitive domain
    if d in DEFINITIVE_DOMAINS:
        return DEFINITIVE_DOMAINS[d]
    for known, cluster in DEFINITIVE_DOMAINS.items():
        if d.endswith("." + known):
            return cluster

    # Reddit special case — classify by content not domain
    if "reddit.com" in d:
        content = f"{t} {description.lower()} {dom_snippet.lower()[:300]}"
        if any(s in content for s in FOCUS_SIGNALS):
            return "research"
        return "social"

    # Layer 2: YouTube DOM override
    if d == "youtube.com":
        content = f"{t} {description.lower()} {dom_snippet.lower()[:300]}"
        if any(s in content for s in FOCUS_SIGNALS):
            return "research"
        return "entertainment"

    # Layer 3: NLI on real content
    content = " ".join(filter(None, [description, dom_snippet[:300], title]))
    if len(content.strip()) > 20:
        try:
            result = get_classifier()(
                content[:512], CLUSTER_NAMES, multi_label=False,
            )
            if result["scores"][0] > 0.3:
                return result["labels"][0]
        except Exception as e:
            print(f"NLI error: {e}")

    # Layer 4: search engine query extraction
    search_engines = [
        "google.com", "search.brave.com", "bing.com",
        "duckduckgo.com", "search.yahoo.com",
    ]
    if any(x in d for x in search_engines):
        query = t
        for suffix in ["- brave search", "- google search", "- bing", "- duckduckgo"]:
            query = query.replace(suffix, "").strip()
        if query and len(query) > 3:
            try:
                result = get_classifier()(query, CLUSTER_NAMES, multi_label=False)
                if result["scores"][0] > 0.35:
                    return result["labels"][0]
            except Exception:
                pass
        return "reference"

    # Domain pattern hints
    if any(x in d for x in [".edu", "university", "college", "academy"]):
        return "research"
    if any(x in d for x in ["docs.", "doc.", "api.", "dev.", "developer."]):
        return "reference"
    if any(x in d for x in ["shop", "store", "buy", "deal", "sale"]):
        return "shopping"
    if any(x in d for x in ["health", "medical", "clinic", "pharma"]):
        return "health"
    if any(x in d for x in ["news", "press", "daily", "times", "post"]):
        return "news"

    return "reference"


def _is_distraction(
    cluster: str,
    domain: str,
    title: str = "",
    dom_snippet: str = "",
    description: str = "",
) -> bool:
    d = _normalize_domain(domain)
    t = title.lower()
    content = f"{t} {description.lower()} {dom_snippet.lower()[:300]}"

    # Always distraction — no exceptions
    if d in ALWAYS_DISTRACTION:
        return True

    # Never distraction if focus signals present
    if any(s in content for s in FOCUS_SIGNALS):
        return False

    # Social platforms — content-aware
    if d in SOCIAL_DOMAINS or "reddit.com" in d:
        # Feed/home pages = distraction
        if any(s in t for s in SHALLOW_SIGNALS):
            return True
        # Has substantive content = not distraction
        if len(dom_snippet) > 300:
            return False
        if cluster == "research":
            return False
        # Default: give social benefit of doubt if not shallow
        return len(dom_snippet) < 100

    # YouTube — by cluster
    if d == "youtube.com":
        return cluster == "entertainment"

    # Entertainment cluster = distraction
    if cluster == "entertainment":
        return True

    return False


def _focus_score(
    is_distraction: bool,
    visit_count: int,
    description: str,
    dom_snippet: str,
    time_spent: int = 0,
    cluster: str = "",
) -> float:
    if is_distraction:
        return round(max(0.05, 0.2 - (visit_count * 0.02)), 2)

    score = 0.45
    if description:                          score += 0.15
    if len(dom_snippet) > 200:               score += 0.10
    if visit_count > 1:                      score += 0.10
    if time_spent > 120:                     score += 0.10
    if time_spent > 300:                     score += 0.10
    if cluster in {"research", "work"}:      score += 0.05
    return min(round(score, 2), 1.0)

# ── Main entry point ───────────────────────────────────────────

def process_tab(tab: dict) -> None:
    try:
        title       = tab.get("title") or ""
        domain      = tab.get("domain") or ""
        url         = tab.get("url") or ""
        session     = str(tab.get("session_id", "unknown"))
        description = tab.get("meta_description") or ""
        dom_snippet = tab.get("dom_snippet") or ""

        # Skip internal pages
        if not url.startswith("http"):
            return
        if "localhost" in domain or not domain:
            return
        if url.startswith("chrome") or url.startswith("about"):
            return

        cluster = _classify_cluster(title, domain, description, dom_snippet)
        distraction = _is_distraction(
            cluster, domain, title, dom_snippet, description
        )

        point_id    = int(hashlib.md5(url.encode()).hexdigest(), 16) % (2**63)
        visit_count = 1
        existing_time = 0

        try:
            existing = get_qdrant().retrieve(
                collection_name=COLLECTION_NAME,
                ids=[point_id],
                with_payload=True,
            )
            if existing:
                visit_count   = existing[0].payload.get("visit_count", 1) + 1
                existing_time = existing[0].payload.get("time_spent", 0)
        except Exception:
            pass

        focus = _focus_score(
            distraction, visit_count, description,
            dom_snippet, existing_time, cluster
        )

        embed_text = " ".join(filter(None, [
            description, dom_snippet[:200], title, domain
        ]))
        vector = get_embedding_model().encode(
            [embed_text], normalize_embeddings=True
        )[0].tolist()

        payload = {
            "node_id":                   f"url_{hashlib.md5(url.encode()).hexdigest()[:12]}",
            "url":                       url,
            "title":                     title,
            "domain":                    domain,
            "session_id":                session,
            "cluster":                   cluster,
            "is_distraction":            distraction,
            "focus_score":               focus,
            "days_since_visit":          0,
            "visit_count":               visit_count,
            "time_spent":                existing_time,
            "scroll_depth":              0.0,
            "tab_closed_without_return": False,
            "saved_for_later":           False,
            "revisited":                 visit_count > 1,
            "is_escape_node":            distraction and visit_count == 1,
            "depth":                     0,
            "meta_description":          description[:200] if description else "",
        }

        get_qdrant().upsert(
            collection_name=COLLECTION_NAME,
            points=[PointStruct(id=point_id, vector=vector, payload=payload)],
        )

        driver = get_neo4j()
        with driver.session() as s:
            s.run("""
                MERGE (n:BrowsingNode {node_id: $node_id})
                SET n.url = $url, n.title = $title, n.domain = $domain,
                    n.session_id = $session_id, n.cluster = $cluster,
                    n.is_distraction = $is_distraction,
                    n.focus_score = $focus_score,
                    n.visit_count = $visit_count, n.depth = 0
                MERGE (sess:Session {session_id: $session_id})
                MERGE (d:Domain {name: $domain})
                MERGE (c:Cluster {name: $cluster})
                MERGE (n)-[:PART_OF]->(sess)
                MERGE (n)-[:HOSTED_ON]->(d)
                MERGE (n)-[:BELONGS_TO]->(c)
            """, {
                "node_id":        f"url_{hashlib.md5(url.encode()).hexdigest()[:12]}",
                "url":            url,
                "title":          title,
                "domain":         domain,
                "session_id":     session,
                "cluster":        cluster,
                "is_distraction": distraction,
                "focus_score":    focus,
                "visit_count":    visit_count,
            })

        status = "revisit" if visit_count > 1 else "new"
        print(f"✓ [{status}][{cluster}][distraction={distraction}] {title[:50]}")

    except Exception as e:
        print(f"✗ ingest_realtime error: {e}")