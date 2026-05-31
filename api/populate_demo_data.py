"""
Tab Constellation — Demo Data Populator (v2)
=============================================
Generates convincing synthetic browsing data with:
  - Proper rabbit holes: deep chains (depth 5-10) that spiral across clusters
  - Correct depth values per hop within a session
  - Proper referrer_url chains so same-tab spiral detection works
  - Realistic days_since_visit spread so ALL time windows show different data
  - Distraction nodes with real time_spent so crash site shows data

Run:
  cd api
  source venv/bin/activate
  python populate_demo_data.py --clear

Options:
  --nodes N    Total nodes to generate (default: 150)
  --days  N    Spread over last N days (default: 30)
  --clear      Wipe collection before inserting
"""

import argparse
import hashlib
import random
import time
from collections import Counter

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct, PayloadSchemaType,
)
from sentence_transformers import SentenceTransformer

# ── Config ─────────────────────────────────────────────────────
QDRANT_URL      = "http://localhost:6333"
COLLECTION_NAME = "tab_constellation"
VECTOR_DIM      = 384
NEO4J_URI       = "bolt://localhost:7687"
NEO4J_USER      = "neo4j"
NEO4J_PASS      = "constellation"
EMBED_MODEL     = "sentence-transformers/all-MiniLM-L6-v2"

# ── Site pool ──────────────────────────────────────────────────
# (cluster, domain, title, description)
SITES = [
    # research
    ("research", "arxiv.org",           "Attention Is All You Need — Transformer Architecture",        "Seminal paper on transformer models and self-attention mechanisms for NLP"),
    ("research", "arxiv.org",           "RLHF: Reinforcement Learning from Human Feedback",            "Training language models using human preference data to improve alignment"),
    ("research", "arxiv.org",           "Retrieval-Augmented Generation for Knowledge-Intensive NLP",  "RAG combines parametric and non-parametric memory for open-domain QA"),
    ("research", "arxiv.org",           "Scaling Laws for Neural Language Models",                     "Empirical study of how model performance scales with compute and data"),
    ("research", "huggingface.co",      "sentence-transformers/all-MiniLM-L6-v2 Model Card",          "Compact sentence embedding model optimized for semantic similarity tasks"),
    ("research", "paperswithcode.com",  "State of the Art: Image Segmentation Benchmarks",            "Leaderboards and reproducible results for image segmentation research"),
    ("research", "semanticscholar.org", "Graph Neural Networks: A Review of Methods and Applications", "Survey of GNN architectures, training techniques and real-world applications"),
    ("research", "openai.com",          "GPT-4 Technical Report",                                     "Multimodal large language model with improved reasoning and instruction following"),
    ("research", "anthropic.com",       "Constitutional AI: Harmlessness from AI Feedback",           "Training AI systems to be helpful, harmless, and honest using AI feedback"),
    ("research", "qdrant.tech",         "Qdrant Vector Database — Filtering and Payload Indexes",     "How to combine vector search with payload filters for hybrid queries"),
    ("research", "pytorch.org",         "PyTorch Tutorial: Building a Neural Network from Scratch",   "Step-by-step guide to building and training neural networks in PyTorch"),
    ("research", "coursera.org",        "Deep Learning Specialization — Week 3 Notes",                "Lecture notes covering convolutional networks and sequence models"),
    # work
    ("work", "github.com",       "tab-constellation — PR 42: Add Neo4j integration",          "Graph database layer for tracking browsing sessions and referrer chains"),
    ("work", "github.com",       "qdrant/qdrant — Issues: Payload index performance",          "Discussion on optimizing payload index queries for large collections"),
    ("work", "github.com",       "react — Issues: useEffect cleanup not firing on unmount",    "Bug report and workaround for useEffect cleanup in React strict mode"),
    ("work", "notion.so",        "Sprint Planning — Tab Constellation Q2 Roadmap",             "Feature roadmap and sprint backlog for the Tab Constellation project"),
    ("work", "linear.app",       "TAB-89: Implement time-window filter for insights API",      "Backend and frontend changes to support hours-based time filtering"),
    ("work", "stackoverflow.com","FastAPI background tasks with uvicorn reload — solution",    "Running background tasks in FastAPI without blocking the main event loop"),
    ("work", "notion.so",        "Architecture Decision: Qdrant vs Pinecone vs Weaviate",      "Comparison of vector databases for production semantic search workloads"),
    ("work", "gitlab.com",       "CI/CD Pipeline — Tab Constellation Docker Build Config",     "Automated build and test pipeline configuration for the extension backend"),
    # entertainment
    ("entertainment", "youtube.com", "The Most Satisfying Mechanical Keyboard Build ASMR",    ""),
    ("entertainment", "youtube.com", "Top 10 Anime of 2025 — Year in Review Compilation",     ""),
    ("entertainment", "youtube.com", "Gordon Ramsay Ultimate Guide to Perfect Pasta",         ""),
    ("entertainment", "youtube.com", "How Elden Ring World Design Changes Everything",        ""),
    ("entertainment", "youtube.com", "I Spent 100 Days in Hardcore Minecraft and Here's What Happened", ""),
    ("entertainment", "youtube.com", "Every Marvel Movie Ranked Worst to Best 2025",         ""),
    ("entertainment", "netflix.com", "Stranger Things Season 5 Episode 3 Recap",             ""),
    ("entertainment", "twitch.tv",   "xQc Minecraft Hardcore Day 47 Full Stream",            ""),
    ("entertainment", "spotify.com", "Lofi Hip Hop Radio Beats to Study and Relax To",       ""),
    ("entertainment", "9gag.com",    "9GAG Hot Posts Today Trending Memes",                  ""),
    # social
    ("social", "twitter.com",  "Andrej Karpathy on X: New miniGPT tutorial deep dive",  ""),
    ("social", "twitter.com",  "Sam Altman on X: Thoughts on AGI timelines 2025",       ""),
    ("social", "twitter.com",  "Yann LeCun on X: Debate on path to general intelligence",""),
    ("social", "reddit.com",   "r/MachineLearning Weekly Discussion Thread",            "Discussion on recent ML papers and industry news from the community"),
    ("social", "reddit.com",   "r/LocalLLaMA Running Llama 3 on 8GB VRAM tips",        "Community tips for running large language models on consumer hardware"),
    ("social", "reddit.com",   "r/programming Show HN: I built a browser extension",   "Community reactions to a new open source browser productivity tool"),
    ("social", "reddit.com",   "r/webdev What JS framework should I learn in 2025",    ""),
    ("social", "linkedin.com", "LinkedIn Feed Connections Activity Updates",            ""),
    ("social", "threads.net",  "Threads Following Feed Latest Posts",                  ""),
    # news
    ("news", "techcrunch.com",        "OpenAI Raises 6.6B at 157B Valuation Round",              "The AI startup latest funding round values it higher than most Fortune 500"),
    ("news", "theverge.com",          "Apple Intelligence arrives on iPhone Everything it can do","Apple AI features roll out including writing tools and image generation"),
    ("news", "arstechnica.com",       "The GPU shortage is finally over whats next for AI",      "Analysis of the semiconductor supply chain and GPU availability in 2025"),
    ("news", "wired.com",             "Inside the AI Lab Racing to Build AGI Profile",           "Profile of a leading AI research organization and their technical approach"),
    ("news", "news.ycombinator.com",  "Ask HN What are you building with LLMs in 2025",         "Community thread on practical LLM applications and side projects"),
    ("news", "techcrunch.com",        "Mistral AI releases open-weight model beating GPT-4",     "French AI startup latest model outperforms competitors on key benchmarks"),
    # shopping
    ("shopping", "amazon.com", "Keychron K2 Pro Wireless Mechanical Keyboard Hot Pink",   ""),
    ("shopping", "amazon.com", "NVIDIA RTX 4070 Super 12GB Graphics Card Best Price",    ""),
    ("shopping", "amazon.com", "Logitech MX Master 3S Wireless Performance Mouse",       ""),
    ("shopping", "ebay.com",   "Vintage ThinkPad X230 Good Condition Low Price",         ""),
    # finance
    ("finance", "bloomberg.com",    "Fed Signals Rate Cuts as Inflation Eases Globally",  "Federal Reserve policy update and market reaction analysis for investors"),
    ("finance", "tradingview.com",  "NVDA NVIDIA Corporation Daily Chart Analysis",       ""),
    ("finance", "investopedia.com", "Dollar Cost Averaging Complete Beginner Guide",      "Investment strategy for reducing the impact of market volatility over time"),
    # communication
    ("communication", "mail.google.com",     "Gmail Inbox 3 unread messages",     ""),
    ("communication", "slack.com",           "Slack tab-constellation channel",   ""),
    ("communication", "calendar.google.com", "Google Calendar This Week Events",  ""),
    # reference
    ("reference", "developer.mozilla.org", "MDN Array prototype reduce JavaScript Reference",    "Complete reference for the JavaScript reduce method with live examples"),
    ("reference", "stackoverflow.com",     "Python How to flatten a nested list efficiently",    "Multiple approaches for flattening nested lists in Python with benchmarks"),
    ("reference", "docs.docker.com",       "Docker Compose Getting Started Guide Official",      "Official guide for defining multi-container applications with Docker Compose"),
    ("reference", "developer.mozilla.org", "CSS Grid Layout Complete Reference Guide MDN",       "Comprehensive reference for CSS Grid with visual examples and browser support"),
    ("reference", "en.wikipedia.org",      "Vector database Wikipedia overview",                 "Encyclopedia article on vector databases and approximate nearest neighbor search"),
    # health
    ("health", "webmd.com",      "Eye strain from screens Prevention and Treatment Tips",  "Tips for reducing digital eye strain during extended computer use at desk"),
    ("health", "healthline.com", "Benefits of Pomodoro Technique for Deep Focus Work",    "How structured work intervals improve concentration and reduce mental burnout"),
]

# ── Cluster properties ─────────────────────────────────────────
FOCUS_CLUSTERS       = {"research", "work", "reference"}
DISTRACTION_CLUSTERS = {"entertainment", "social", "shopping"}
DISTRACTION_DOMAINS  = {"youtube.com","netflix.com","twitch.tv","9gag.com","twitter.com","threads.net","instagram.com"}

# ── Rabbit hole templates ──────────────────────────────────────
# Each template is a sequence of clusters that defines a believable spiral
RABBIT_HOLE_TEMPLATES = [
    # Classic focus → distraction spiral
    ["work",    "work",    "research", "social",        "entertainment", "entertainment", "social"],
    ["research","research","research", "news",          "social",        "entertainment", "entertainment"],
    ["work",    "research","reference","news",          "social",        "social",        "entertainment"],
    # Procrastination loop
    ["work",    "news",    "social",   "entertainment", "shopping",      "social",        "entertainment"],
    ["research","news",    "news",     "social",        "social",        "entertainment", "youtube spiral"],
    # Deep research rabbit hole (no distraction — pure cluster shifts)
    ["research","research","reference","research",      "work",          "reference",     "research"],
    ["work",    "work",    "reference","research",      "research",      "reference",     "work"],
    # Short but deep
    ["work",    "social",  "entertainment","entertainment","entertainment"],
    ["research","research","social",   "entertainment", "entertainment"],
]

SITES_BY_CLUSTER: dict[str, list] = {}
for row in SITES:
    SITES_BY_CLUSTER.setdefault(row[0], []).append(row)
# add youtube-spiral as alias for entertainment
SITES_BY_CLUSTER["youtube spiral"] = [r for r in SITES if r[1] == "youtube.com"]


# ── Helpers ────────────────────────────────────────────────────

def url_hash(url: str) -> int:
    return int(hashlib.md5(url.encode()).hexdigest(), 16) % (2**63)

def make_node_id(url: str) -> str:
    return f"url_{hashlib.md5(url.encode()).hexdigest()[:12]}"

def make_url(domain: str, title: str, salt: int) -> str:
    slug = (title.lower()[:40]
            .replace(" ", "-").replace(":", "").replace("'", "")
            .replace(",", "").replace(".", "").replace("/", ""))
    return f"https://{domain}/{slug}-{salt}"

def calc_distraction(cluster: str, domain: str) -> bool:
    if domain in DISTRACTION_DOMAINS:
        return True
    if cluster in FOCUS_CLUSTERS:
        return False
    if cluster in DISTRACTION_CLUSTERS:
        return random.random() < 0.75
    return False

def calc_focus(distraction: bool, cluster: str, description: str) -> float:
    if distraction:
        return round(random.uniform(0.05, 0.25), 2)
    base = 0.45
    if cluster in FOCUS_CLUSTERS:
        base += 0.25
    if description:
        base += 0.1
    base += random.uniform(-0.08, 0.12)
    return round(min(max(base, 0.1), 1.0), 2)

def calc_time_spent(distraction: bool, cluster: str) -> int:
    if distraction:
        return random.randint(120, 1200)   # 2min–20min on distractions
    if cluster in FOCUS_CLUSTERS:
        return random.randint(300, 3600)   # 5min–1hr on focus work
    return random.randint(60, 600)

def pick_site(cluster: str) -> tuple:
    pool = SITES_BY_CLUSTER.get(cluster, SITES_BY_CLUSTER["reference"])
    return random.choice(pool)


# ── Session generators ─────────────────────────────────────────

def make_rabbit_hole_session(session_id: str, days_ago: int) -> list[dict]:
    """Generate one deep rabbit hole session using a template."""
    template = random.choice(RABBIT_HOLE_TEMPLATES)
    nodes = []
    referrer_url = ""
    prev_cluster = ""

    for depth, cluster in enumerate(template):
        row = pick_site(cluster)
        _, domain, title, description = row
        salt = random.randint(1000, 9999)
        url = make_url(domain, title, salt)

        distracted  = calc_distraction(cluster, domain)
        fscore      = calc_focus(distracted, cluster, description)
        time_spent  = calc_time_spent(distracted, cluster)
        visit_count = random.choices([1, 2], weights=[0.8, 0.2])[0]
        is_escape   = distracted and depth > 0 and not nodes[-1]["is_distraction"] if nodes else False

        nodes.append({
            "node_id":                   make_node_id(url),
            "url":                       url,
            "title":                     title,
            "domain":                    domain,
            "cluster":                   cluster if cluster != "youtube spiral" else "entertainment",
            "session_id":                session_id,
            "days_since_visit":          days_ago,
            "visit_count":               visit_count,
            "time_spent":                time_spent,
            "scroll_depth":              round(random.uniform(0.3, 1.0) if not distracted else random.uniform(0.05, 0.4), 2),
            "tab_closed_without_return": random.random() < 0.15,
            "saved_for_later":           random.random() < 0.08 and cluster in FOCUS_CLUSTERS,
            "revisited":                 visit_count > 1,
            "is_distraction":            distracted,
            "is_escape_node":            bool(is_escape),
            "focus_score":               fscore,
            "depth":                     depth,
            "referrer_url":              referrer_url,
            "meta_description":          description[:200] if description else "",
            "tab_id":                    f"tab_{random.randint(1, 999):03d}",
        })
        referrer_url = url
        prev_cluster = cluster

    return nodes


def make_normal_session(session_id: str, days_ago: int, length: int = None) -> list[dict]:
    """Generate a normal focused browsing session (2-5 nodes, same cluster)."""
    if length is None:
        length = random.randint(4, 8)
    primary_cluster = random.choice(list(SITES_BY_CLUSTER.keys()))
    if primary_cluster == "youtube spiral":
        primary_cluster = "entertainment"
    nodes = []
    referrer_url = ""

    for depth in range(length):
        # Occasional small drift
        cluster = primary_cluster if random.random() < 0.75 else random.choice(list(FOCUS_CLUSTERS))
        row = pick_site(cluster)
        _, domain, title, description = row
        salt = random.randint(1000, 9999)
        url = make_url(domain, title, salt)

        distracted  = calc_distraction(cluster, domain)
        fscore      = calc_focus(distracted, cluster, description)
        time_spent  = calc_time_spent(distracted, cluster)
        visit_count = random.choices([1, 2, 3], weights=[0.65, 0.25, 0.1])[0]
        is_escape   = distracted and depth > 0 and nodes and not nodes[-1]["is_distraction"]

        nodes.append({
            "node_id":                   make_node_id(url),
            "url":                       url,
            "title":                     title,
            "domain":                    domain,
            "cluster":                   cluster,
            "session_id":                session_id,
            "days_since_visit":          days_ago,
            "visit_count":               visit_count,
            "time_spent":                time_spent,
            "scroll_depth":              round(random.uniform(0.3, 1.0) if not distracted else random.uniform(0.05, 0.4), 2),
            "tab_closed_without_return": random.random() < 0.15,
            "saved_for_later":           random.random() < 0.08 and cluster in FOCUS_CLUSTERS,
            "revisited":                 visit_count > 1,
            "is_distraction":            distracted,
            "is_escape_node":            bool(is_escape),
            "focus_score":               fscore,
            "depth":                     depth,
            "referrer_url":              referrer_url,
            "meta_description":          description[:200] if description else "",
            "tab_id":                    f"tab_{random.randint(1, 999):03d}",
        })
        referrer_url = url

    return nodes


def generate_nodes(n_nodes: int, n_days: int) -> list[dict]:
    """
    Build a realistic dataset with:
    - Guaranteed rabbit holes spread across days
    - Normal sessions filling the rest
    - days_since_visit correctly set per day
    """
    all_nodes: list[dict] = []
    session_counter = 0

    # ── Guarantee rabbit holes at different time windows ────────
    # Today / yesterday (6H–24H window)
    for _ in range(5):
        sid = f"session_{session_counter:04d}"; session_counter += 1
        all_nodes.extend(make_rabbit_hole_session(sid, days_ago=0))

    # 1-2 days ago (2D window)
    for _ in range(2):
        sid = f"session_{session_counter:04d}"; session_counter += 1
        all_nodes.extend(make_rabbit_hole_session(sid, days_ago=random.randint(1, 2)))

    # 3-6 days ago (1W window)
    for _ in range(4):
        sid = f"session_{session_counter:04d}"; session_counter += 1
        all_nodes.extend(make_rabbit_hole_session(sid, days_ago=random.randint(3, 6)))

    # 7-14 days ago
    for _ in range(2):
        sid = f"session_{session_counter:04d}"; session_counter += 1
        all_nodes.extend(make_rabbit_hole_session(sid, days_ago=random.randint(7, 14)))

    # 15-29 days ago (1M window)
    for _ in range(2):
        sid = f"session_{session_counter:04d}"; session_counter += 1
        all_nodes.extend(make_rabbit_hole_session(sid, days_ago=random.randint(15, 29)))

    # ── Fill remaining quota with normal sessions ───────────────
    remaining = n_nodes - len(all_nodes)
    nodes_per_day = max(1, remaining // n_days)

    for day_offset in range(n_days):
        days_ago = n_days - day_offset
        day_target = nodes_per_day + random.randint(-2, 2)
        day_nodes = 0

        while day_nodes < day_target:
            sid = f"session_{session_counter:04d}"; session_counter += 1
            length = random.randint(4, 8)
            batch = make_normal_session(sid, days_ago=days_ago, length=length)
            all_nodes.extend(batch)
            day_nodes += len(batch)

    # Trim to exact count
    random.shuffle(all_nodes)
    return all_nodes[:n_nodes]


# ── Qdrant ─────────────────────────────────────────────────────

def ensure_collection(client: QdrantClient, clear: bool) -> None:
    existing = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME in existing:
        if clear:
            client.delete_collection(COLLECTION_NAME)
            print(f"  Cleared '{COLLECTION_NAME}'")
        else:
            print(f"  Collection exists — appending")
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
    print(f"  Created collection '{COLLECTION_NAME}'")


def upsert_to_qdrant(client: QdrantClient, nodes: list[dict], model: SentenceTransformer) -> None:
    print(f"\nGenerating embeddings for {len(nodes)} nodes...")
    texts = [
        f"{n['title']} {n['domain']} {n['cluster']} {n['meta_description']}"
        for n in nodes
    ]
    t0 = time.time()
    vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=True).tolist()
    print(f"Embeddings done in {time.time()-t0:.1f}s")

    points = [
        PointStruct(id=url_hash(n["url"]), vector=v, payload=n)
        for n, v in zip(nodes, vectors)
    ]
    batch_size = 50
    for i in range(0, len(points), batch_size):
        chunk = points[i:i+batch_size]
        client.upsert(collection_name=COLLECTION_NAME, points=chunk)
        print(f"  Batch {i//batch_size+1}/{-(-len(points)//batch_size)} — {len(chunk)} points")

    print(f"\nQdrant total: {client.count(COLLECTION_NAME).count} points")


# ── Neo4j ──────────────────────────────────────────────────────

def upsert_to_neo4j(nodes: list[dict]) -> None:
    """
    Insert nodes grouped by session, ordered by depth.
    This guarantees FOLLOWED_BY edges are built correctly —
    depth=0 is always in Neo4j before depth=1 tries to link to it.
    """
    try:
        from neo4j import GraphDatabase
        from collections import defaultdict
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
        print(f"\nWriting {len(nodes)} nodes to Neo4j...")

        # Group by session, sort each session by depth
        sessions: dict = defaultdict(list)
        for n in nodes:
            sessions[n["session_id"]].append(n)
        for sid in sessions:
            sessions[sid].sort(key=lambda x: x["depth"])

        # Flatten back in session-depth order
        ordered = [n for sid in sessions for n in sessions[sid]]

        with driver.session() as s:
            for i, n in enumerate(ordered):
                # Upsert the node
                s.run("""
                    MERGE (node:BrowsingNode {node_id: $node_id})
                    SET node.url            = $url,
                        node.title          = $title,
                        node.domain         = $domain,
                        node.session_id     = $session_id,
                        node.cluster        = $cluster,
                        node.is_distraction = $is_distraction,
                        node.focus_score    = $focus_score,
                        node.visit_count    = $visit_count,
                        node.depth          = $depth,
                        node.ingested_at    = datetime()
                    MERGE (sess:Session  {session_id: $session_id})
                    MERGE (d:Domain      {name: $domain})
                    MERGE (c:Cluster     {name: $cluster})
                    MERGE (node)-[:PART_OF]   ->(sess)
                    MERGE (node)-[:HOSTED_ON] ->(d)
                    MERGE (node)-[:BELONGS_TO]->(c)
                """, n)

                # Build FOLLOWED_BY using referrer_url — now guaranteed to exist
                # since we process depth=0 before depth=1 etc.
                if n.get("referrer_url"):
                    s.run("""
                        MATCH (prev:BrowsingNode {url: $ref})
                        MATCH (curr:BrowsingNode {node_id: $nid})
                        MERGE (prev)-[:FOLLOWED_BY]->(curr)
                    """, {"ref": n["referrer_url"], "nid": n["node_id"]})

                if (i+1) % 30 == 0:
                    print(f"  Neo4j: {i+1}/{len(ordered)}")

        driver.close()
        print("Neo4j done")
    except Exception as e:
        print(f"Neo4j skipped: {e}")


# ── Summary ────────────────────────────────────────────────────

def print_summary(nodes: list[dict]) -> None:
    clusters     = Counter(n["cluster"]         for n in nodes)
    days_dist    = Counter(n["days_since_visit"] for n in nodes)
    distractions = sum(1 for n in nodes if n["is_distraction"])
    sessions     = len(set(n["session_id"]       for n in nodes))
    deep_nodes   = sum(1 for n in nodes if n["depth"] >= 3)

    print("\n─── Demo Data Summary ──────────────────────────")
    print(f"  Total nodes    : {len(nodes)}")
    print(f"  Sessions       : {sessions}")
    print(f"  Distractions   : {distractions} ({distractions*100//len(nodes)}%)")
    print(f"  Deep nodes (3+): {deep_nodes}  ← these form rabbit holes")
    print(f"  Days spread    : 0 – {max(days_dist)} days ago")
    print(f"  Today (0d)     : {days_dist.get(0,0)} nodes  ← visible in 6H/12H/24H")
    print(f"  Last 2 days    : {sum(v for k,v in days_dist.items() if k<=2)} nodes  ← 2D window")
    print(f"  Last 7 days    : {sum(v for k,v in days_dist.items() if k<=7)} nodes  ← 1W window")
    print(f"\n  Clusters:")
    for cluster, count in clusters.most_common():
        bar = "█" * max(1, count*25//len(nodes))
        print(f"    {cluster:<16} {bar} {count}")
    print("────────────────────────────────────────────────\n")


# ── Entry ──────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--nodes", type=int, default=150)
    parser.add_argument("--days",  type=int, default=30)
    parser.add_argument("--clear", action="store_true")
    args = parser.parse_args()

    print("Tab Constellation — Demo Data Populator v2")
    print(f"nodes={args.nodes}  days={args.days}  clear={args.clear}\n")

    nodes = generate_nodes(args.nodes, args.days)
    print_summary(nodes)

    print("Loading embedding model...")
    model = SentenceTransformer(EMBED_MODEL)
    print("Model ready\n")

    client = QdrantClient(url=QDRANT_URL)
    ensure_collection(client, clear=args.clear)
    upsert_to_qdrant(client, nodes, model)
    upsert_to_neo4j(nodes)

    print("\nDone! Restart your search API and refresh the frontend.")
    print("Tip: switch Crash Site window to 1W or ALL to see distraction data.\n")
