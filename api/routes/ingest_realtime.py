"""
Tab Constellation — Real-time ingestion into Qdrant + Neo4j.
4-layer classification + content-aware distraction detection.
Loads user profile from data/user_profile.json for personalized rules.
"""

from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
from functools import lru_cache
from neo4j import GraphDatabase
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, PayloadSchemaType
from dotenv import load_dotenv

load_dotenv()

# ── Config ─────────────────────────────────────────────────────
QDRANT_URL      = "http://localhost:6333"
COLLECTION_NAME = "tab_constellation"
VECTOR_DIM      = 384
NEO4J_URI       = "bolt://localhost:7687"
NEO4J_USER      = "neo4j"
NEO4J_PASSWORD  = os.environ["NEO4J_PASSWORD"]
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
NLI_MODEL       = "cross-encoder/nli-MiniLM2-L6-H768"

_PROFILE_PATH = Path(__file__).parent.parent / "data" / "user_profile.json"
_USER_PROFILE: dict | None = None

def _load_user_profile() -> dict:
    global _USER_PROFILE
    if _USER_PROFILE is not None:
        return _USER_PROFILE
    if _PROFILE_PATH.exists():
        with open(_PROFILE_PATH) as f:
            _USER_PROFILE = json.load(f)
    else:
        _USER_PROFILE = {"extra_domains": {}, "extra_focus_signals": []}
    return _USER_PROFILE

def reload_user_profile() -> None:
    """Call this after onboarding saves a new profile."""
    global _USER_PROFILE
    _USER_PROFILE = None
    _load_user_profile()

# ── Universal clusters ─────────────────────────────────────────
CLUSTER_NAMES = [
    "research", "work", "entertainment", "shopping",
    "social", "news", "health", "finance",
    "travel", "creative", "reference", "communication",
]

# ── Layer 1: Definitive domain map ─────────────────────────────
DEFINITIVE_DOMAINS: dict[str, str] = {
    # Entertainment
    "netflix.com": "entertainment", "twitch.tv": "entertainment",
    "tiktok.com": "entertainment", "spotify.com": "entertainment",
    "imdb.com": "entertainment", "primevideo.com": "entertainment",
    "disneyplus.com": "entertainment", "hulu.com": "entertainment",
    "soundcloud.com": "entertainment", "9gag.com": "entertainment",
    "buzzfeed.com": "entertainment",
    # Sports
    "premierleague.com": "entertainment", "espn.com": "entertainment",
    "nba.com": "entertainment", "nfl.com": "entertainment",
    "cricbuzz.com": "entertainment", "sofascore.com": "entertainment",
    "flashscore.com": "entertainment", "vlr.gg": "entertainment",
    "hltv.org": "entertainment", "liquipedia.net": "entertainment",
    "fifa.com": "entertainment", "uefa.com": "entertainment",
    # Social
    "twitter.com": "social", "x.com": "social",
    "instagram.com": "social", "facebook.com": "social",
    "linkedin.com": "social", "threads.net": "social",
    "pinterest.com": "social", "snapchat.com": "social",
    # Reference
    "en.wikipedia.org": "reference", "wikipedia.org": "reference",
    "stackoverflow.com": "reference", "stackexchange.com": "reference",
    "developer.mozilla.org": "reference", "docs.python.org": "reference",
    "kubernetes.io": "reference", "docs.docker.com": "reference",
    "devdocs.io": "reference", "w3schools.com": "reference",
    "man7.org": "reference",
    # Research
    "arxiv.org": "research", "huggingface.co": "research",
    "paperswithcode.com": "research", "semanticscholar.org": "research",
    "pubmed.ncbi.nlm.nih.gov": "research", "researchgate.net": "research",
    "openai.com": "research", "anthropic.com": "research",
    "deepmind.google": "research", "mistral.ai": "research",
    "qdrant.tech": "research", "pytorch.org": "research",
    "tensorflow.org": "research",
    # Work / Code
    "github.com": "work", "gitlab.com": "work",
    "bitbucket.org": "work", "jira.atlassian.com": "work",
    "notion.so": "work", "trello.com": "work",
    "asana.com": "work", "clickup.com": "work",
    "linear.app": "work", "vllm.ai": "work",
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
    "beginner", "complete guide", "step by step", "how to build",
]

SHALLOW_SIGNALS = [
    "feed", "home", "trending", "explore", "timeline",
    "for you", "recommended", "watch later", "subscriptions",
    "notifications", "messages", "stories",
]

ALWAYS_DISTRACTION = {
    "netflix.com", "tiktok.com", "twitch.tv",
    "9gag.com", "buzzfeed.com", "instagram.com",
}

SOCIAL_DOMAINS = {
    "reddit.com", "old.reddit.com", "twitter.com", "x.com",
    "facebook.com", "linkedin.com", "threads.net",
}

def _build_classification_text(tab: dict) -> str:
    """
    Compose the best-quality text for NLI classification.
    Priority: og metadata first (cleanest), then h1, then path tokens,
    then dom_snippet (noisier). NLI weights the start of the input more,
    so high-signal fields go first.
    """
    parts = [
        tab.get("og_title") or tab.get("title") or "",
        tab.get("og_description") or tab.get("meta_description") or "",
        tab.get("h1") or "",
        tab.get("path_tokens") or "",
        (tab.get("dom_snippet") or "")[:600],  # noisier; keep short
    ]
    # Dedupe near-identical lines (og_title often == title)
    seen = set()
    deduped = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        key = p.lower()[:80]
        if key in seen:
            continue
        seen.add(key)
        deduped.append(p)
    return " ".join(deduped)
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
        ("referrer_url",              PayloadSchemaType.KEYWORD),
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
    url: str = "",
) -> str:
    d = _normalize_domain(domain)
    t = title.lower()
 
    # Layer 0: user profile domain rules
    profile = _load_user_profile()
    user_domains = profile.get("extra_domains", {})
    if d in user_domains:
        return user_domains[d]
    for known, cluster in user_domains.items():
        if d.endswith("." + known):
            return cluster
 
    # Layer 1: definitive domains (skip content-dependent ones)
    CONTENT_DEPENDENT = {"youtube.com", "reddit.com", "old.reddit.com",
                          "twitter.com", "x.com", "linkedin.com",
                          "medium.com", "substack.com"}
 
    if d in DEFINITIVE_DOMAINS and d not in CONTENT_DEPENDENT:
        return DEFINITIVE_DOMAINS[d]
    for known, cluster in DEFINITIVE_DOMAINS.items():
        if known not in CONTENT_DEPENDENT and d.endswith("." + known):
            return cluster
 
    # Reddit — use subreddit path as primary signal
    if "reddit.com" in d:
        path = url.split("reddit.com")[-1] if "reddit.com" in url else ""
        # Extract subreddit name: /r/MachineLearning → "MachineLearning"
        parts = [p for p in path.split("/") if p and p not in ("r", "comments", "wiki")]
        subreddit = parts[0] if parts else ""
        if subreddit and len(subreddit) > 2:
            try:
                result = get_classifier()(
                    subreddit, CLUSTER_NAMES, multi_label=False
                )
                if result["scores"][0] > 0.25:
                    return result["labels"][0]
            except Exception:
                pass
        # Fallback: use title + dom_snippet
        content = f"{t} {description.lower()} {dom_snippet.lower()[:300]}"
        all_focus = FOCUS_SIGNALS + profile.get("extra_focus_signals", [])
        if any(s in content for s in all_focus):
            return "research"
        return "social"
 
    # YouTube — use video title from youtube_data (passed via dom_snippet)
    if d == "youtube.com":
        content = f"{t} {description.lower()} {dom_snippet.lower()[:300]}"
        all_focus = FOCUS_SIGNALS + profile.get("extra_focus_signals", [])
        if any(s in content for s in all_focus):
            return "research"
        # Check path — /watch means video page
        path = url.split("youtube.com")[-1] if "youtube.com" in url else ""
        if path in ["", "/", "/feed/subscriptions", "/feed/trending", "/feed/explore"]:
            return "entertainment"
        # For video pages with no focus signal — use NLI on content
        if len(content.strip()) > 20:
            try:
                result = get_classifier()(content[:512], CLUSTER_NAMES, multi_label=False)
                if result["scores"][0] > 0.3:
                    return result["labels"][0]
            except Exception:
                pass
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
        # Extract query from URL params — more reliable than title
        try:
            from urllib.parse import urlparse, parse_qs
            params = parse_qs(urlparse(url).query)
            query = params.get("q", [""])[0]
        except Exception:
            query = t
            for suffix in ["- brave search", "- google search", "- bing"]:
                query = query.replace(suffix, "").strip()
 
        if query and len(query) > 3:
            try:
                result = get_classifier()(query, CLUSTER_NAMES, multi_label=False)
                if result["scores"][0] > 0.3:
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

    # Always distraction
    if d in ALWAYS_DISTRACTION:
        return True

    # Never distraction if research/work cluster
    if cluster in {"research", "work", "reference"}:
        return False

    # User focus signals override
    profile = _load_user_profile()
    all_focus = FOCUS_SIGNALS + profile.get("extra_focus_signals", [])
    if any(s in content for s in all_focus):
        return False

    # Social — content aware
    if d in SOCIAL_DOMAINS or "reddit.com" in d:
        if any(s in t for s in SHALLOW_SIGNALS):
            return True
        if len(dom_snippet) > 300:
            return False
        if cluster == "research":
            return False
        return len(dom_snippet) < 100

    # YouTube — by cluster
    if d == "youtube.com":
        return cluster == "entertainment"

    # Entertainment cluster
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


# ── process_tab  ────────────────────
 
def process_tab(tab: dict) -> None:
    try:
        title       = tab.get("title") or ""
        domain      = tab.get("domain") or ""
        url         = tab.get("url") or ""
        session     = str(tab.get("session_id", "unknown"))
        description = tab.get("meta_description") or tab.get("og_description") or ""
        dom_snippet = tab.get("dom_snippet") or ""
        tab_id      = str(tab.get("tab_id", ""))
 
        if not url.startswith("http"):
            return
        if "localhost" in domain or not domain:
            return
        if url.startswith("chrome") or url.startswith("about"):
            return
 
        # ── Enrich dom_snippet BEFORE classification ───────────
 
        # YouTube: use video title/channel from enriched data
        youtube_data = tab.get("youtube_data") or {}
        if "youtube.com" in domain and youtube_data:
            youtube_title   = youtube_data.get("video_title", "")
            youtube_channel = youtube_data.get("channel", "")
            youtube_desc    = youtube_data.get("video_description", "")
            youtube_cat     = youtube_data.get("category", "")
            if youtube_title:
                dom_snippet = f"{youtube_title} {youtube_channel} {youtube_desc} {youtube_cat}"

        if "youtube.com" in domain:
            print(f"DEBUG youtube_data: {youtube_data}")
            print(f"DEBUG dom_snippet: {dom_snippet[:100]}")
 
        # All sites: enrich with og_title, h1, path_tokens if dom_snippet is weak
        og_title    = tab.get("og_title") or ""
        h1          = tab.get("h1") or ""
        path_tokens = tab.get("path_tokens") or ""
        if len(dom_snippet) < 100 and (og_title or h1 or path_tokens):
            dom_snippet = " ".join(filter(None, [og_title, h1, path_tokens, dom_snippet]))
 
        # Use og_description as fallback for description
        if not description:
            description = tab.get("og_description") or ""
 
        # ── Classify with enriched content ─────────────────────
        cluster     = _classify_cluster(title, domain, description, dom_snippet, url)
        distraction = _is_distraction(cluster, domain, title, dom_snippet, description)
        point_id    = int(hashlib.md5(url.encode()).hexdigest(), 16) % (2**63)
        node_id     = f"url_{hashlib.md5(url.encode()).hexdigest()[:12]}"
 
        visit_count   = 1
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
            dom_snippet, existing_time, cluster,
        )

        embed_text = " ".join(filter(None, [
            description, dom_snippet[:200], title, domain
        ]))
        vector = get_embedding_model().encode(
            [embed_text], normalize_embeddings=True
        )[0].tolist()

        # Real visit time so the frontend can filter by hour, not just day.
        # Prefer the timestamp the extension sent; fall back to now().
        last_visited_at = tab.get("timestamp") or datetime.now(timezone.utc).isoformat()

        payload = {
            "node_id":                   node_id,
            "url":                       url,
            "title":                     title,
            "domain":                    domain,
            "session_id":                session,
            "cluster":                   cluster,
            "is_distraction":            distraction,
            "focus_score":               focus,
            "days_since_visit":          0,
            "ingested_at":               __import__("time").time(),
            "visit_count":               visit_count,
            "time_spent":                existing_time,
            "scroll_depth":              0.0,
            "tab_closed_without_return": False,
            "saved_for_later":           False,
            "revisited":                 visit_count > 1,
            "is_escape_node":            distraction and visit_count == 1,
            "depth":                     0,
            "meta_description":          description[:200] if description else "",
            "tab_id":                    tab_id,
            "referrer_url":              (tab.get("referrer_url") or "")[:500],
        }
 
        get_qdrant().upsert(
            collection_name=COLLECTION_NAME,
            points=[PointStruct(id=point_id, vector=vector, payload=payload)],
        )
 
        # ── Neo4j: store node + FOLLOWED_BY edge ───────────────
        driver = get_neo4j()
        with driver.session() as s:
            s.run("""
                MERGE (n:BrowsingNode {node_id: $node_id})
                SET n.url = $url, n.title = $title, n.domain = $domain,
                    n.session_id = $session_id, n.cluster = $cluster,
                    n.is_distraction = $is_distraction,
                    n.focus_score = $focus_score,
                    n.visit_count = $visit_count,
                    n.depth = 0,
                    n.ingested_at = datetime()
                MERGE (sess:Session {session_id: $session_id})
                MERGE (d:Domain {name: $domain})
                MERGE (c:Cluster {name: $cluster})
                MERGE (n)-[:PART_OF]->(sess)
                MERGE (n)-[:HOSTED_ON]->(d)
                MERGE (n)-[:BELONGS_TO]->(c)
            """, {
                "node_id":        node_id,
                "url":            url,
                "title":          title,
                "domain":         domain,
                "session_id":     session,
                "cluster":        cluster,
                "is_distraction": distraction,
                "focus_score":    focus,
                "visit_count":    visit_count,
            })
 
            # FOLLOWED_BY edge — builds temporal browsing sequence in Neo4j
            s.run("""
                MATCH (prev:BrowsingNode)
                WHERE prev.session_id = $session_id
                  AND prev.node_id <> $node_id
                WITH prev ORDER BY prev.ingested_at DESC LIMIT 1
                MATCH (curr:BrowsingNode {node_id: $node_id})
                MERGE (prev)-[:FOLLOWED_BY]->(curr)
            """, {
                "session_id": session,
                "node_id":    node_id,
            })
 
        status = "revisit" if visit_count > 1 else "new"
        print(f"✓ [{status}][{cluster}][distraction={distraction}] {title[:50]}")
 
    except Exception as e:
        print(f"✗ ingest_realtime error: {e}")
 