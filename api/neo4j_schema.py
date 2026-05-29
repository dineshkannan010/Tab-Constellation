"""
Tab Constellation — Neo4j Schema + Graph Queries
=================================================
Defines the graph schema (constraints, indexes), loads nodes/edges from
mockData.json, and provides graph traversal queries for Rabbit Hole,
session paths, and referrer chains.

Run locally with Docker:
  docker run -p 7474:7474 -p 7687:7687 \\
    -e NEO4J_AUTH=neo4j/constellation \\
    neo4j:5

Then open: http://localhost:7474

Install:
  pip install neo4j

Usage:
  python neo4j_schema.py              # create schema + load mock data
  python neo4j_schema.py --clear      # wipe graph first
  python neo4j_schema.py --queries    # run sample traversal queries
"""

import json
import argparse
from pathlib import Path
from neo4j import GraphDatabase, Driver

# ─── Config ────────────────────────────────────────────────────

NEO4J_URI      = "bolt://localhost:7687"
NEO4J_USER     = "neo4j"
NEO4J_PASSWORD = "constellation"
MOCK_DATA_PATH = Path(__file__).parent / "mockData.json"

# ─── Schema definition ─────────────────────────────────────────
#
# Node labels:
#   (:BrowsingNode)     — every visited page
#   (:Session)          — a browsing session
#   (:Cluster)          — semantic topic cluster
#   (:Domain)           — website domain
#
# Relationship types:
#   (:BrowsingNode)-[:REFERRED_TO]->(:BrowsingNode)   — navigation referrer chain
#   (:BrowsingNode)-[:PART_OF]->(:Session)             — node belongs to session
#   (:BrowsingNode)-[:BELONGS_TO]->(:Cluster)          — node's semantic cluster
#   (:BrowsingNode)-[:HOSTED_ON]->(:Domain)            — node's domain
#   (:BrowsingNode)-[:SIMILAR_TO {weight}]->(:BrowsingNode) — semantic edge from mockData
#
# Properties on BrowsingNode (mirrors QdrantPayload for cross-store consistency):
#   node_id, url, title, domain, visited_at, last_visited_at,
#   days_since_visit, visit_count, time_spent, scroll_depth,
#   tab_closed_without_return, depth, session_id, cluster,
#   is_distraction, focus_score, saved_for_later, revisited, is_escape_node

SCHEMA_QUERIES = [
    # Uniqueness constraints (also create indexes automatically)
    "CREATE CONSTRAINT browsing_node_id IF NOT EXISTS FOR (n:BrowsingNode) REQUIRE n.node_id IS UNIQUE",
    "CREATE CONSTRAINT session_id       IF NOT EXISTS FOR (s:Session)       REQUIRE s.session_id IS UNIQUE",
    "CREATE CONSTRAINT cluster_name     IF NOT EXISTS FOR (c:Cluster)        REQUIRE c.name IS UNIQUE",
    "CREATE CONSTRAINT domain_name      IF NOT EXISTS FOR (d:Domain)         REQUIRE d.name IS UNIQUE",

    # Additional indexes for frequent filter patterns
    "CREATE INDEX browsing_node_cluster         IF NOT EXISTS FOR (n:BrowsingNode) ON (n.cluster)",
    "CREATE INDEX browsing_node_is_distraction  IF NOT EXISTS FOR (n:BrowsingNode) ON (n.is_distraction)",
    "CREATE INDEX browsing_node_days_since      IF NOT EXISTS FOR (n:BrowsingNode) ON (n.days_since_visit)",
    "CREATE INDEX browsing_node_focus_score     IF NOT EXISTS FOR (n:BrowsingNode) ON (n.focus_score)",
    "CREATE INDEX browsing_node_saved_for_later IF NOT EXISTS FOR (n:BrowsingNode) ON (n.saved_for_later)",
    "CREATE INDEX browsing_node_escape          IF NOT EXISTS FOR (n:BrowsingNode) ON (n.is_escape_node)",
    "CREATE INDEX browsing_node_session_id      IF NOT EXISTS FOR (n:BrowsingNode) ON (n.session_id)",
    "CREATE INDEX browsing_node_depth           IF NOT EXISTS FOR (n:BrowsingNode) ON (n.depth)",
]

# ─── Driver factory ────────────────────────────────────────────

def get_driver() -> Driver:
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

# ─── Schema creation ───────────────────────────────────────────

def create_schema(driver: Driver) -> None:
    with driver.session() as session:
        for query in SCHEMA_QUERIES:
            session.run(query)
    print(f"Schema created: {len(SCHEMA_QUERIES)} constraints/indexes applied.")

# ─── Graph loading ─────────────────────────────────────────────

def load_graph(driver: Driver, data: dict) -> None:
    nodes = data["nodes"]
    edges = data["edges"]

    with driver.session() as session:

        # 1. Merge BrowsingNode + related Cluster, Domain, Session nodes
        print("Loading BrowsingNodes...")
        for node in nodes:
            session.run("""
                MERGE (n:BrowsingNode {node_id: $node_id})
                SET
                  n.url                       = $url,
                  n.title                     = $title,
                  n.domain                    = $domain,
                  n.visited_at                = $visited_at,
                  n.last_visited_at           = $last_visited_at,
                  n.days_since_visit          = $days_since_visit,
                  n.visit_count               = $visit_count,
                  n.time_spent                = $time_spent,
                  n.scroll_depth              = $scroll_depth,
                  n.tab_closed_without_return = $tab_closed_without_return,
                  n.referrer                  = $referrer,
                  n.depth                     = $depth,
                  n.session_id                = $session_id,
                  n.cluster                   = $cluster,
                  n.is_distraction            = $is_distraction,
                  n.focus_score               = $focus_score,
                  n.saved_for_later           = $saved_for_later,
                  n.revisited                 = $revisited,
                  n.is_escape_node            = $is_escape_node

                MERGE (s:Session {session_id: $session_id})

                MERGE (c:Cluster {name: $cluster})

                MERGE (d:Domain {name: $domain})

                MERGE (n)-[:PART_OF]->(s)
                MERGE (n)-[:BELONGS_TO]->(c)
                MERGE (n)-[:HOSTED_ON]->(d)
            """, {
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
            })

        # 2. REFERRED_TO edges (referrer chain)
        print("Loading referrer chains (REFERRED_TO)...")
        for node in nodes:
            if node.get("referrer"):
                session.run("""
                    MATCH (src:BrowsingNode {node_id: $referrer})
                    MATCH (dst:BrowsingNode {node_id: $node_id})
                    MERGE (src)-[:REFERRED_TO]->(dst)
                """, {"referrer": node["referrer"], "node_id": node["id"]})

        # 3. SIMILAR_TO edges (semantic similarity from mockData edges)
        print("Loading semantic edges (SIMILAR_TO)...")
        for edge in edges:
            session.run("""
                MATCH (src:BrowsingNode {node_id: $source})
                MATCH (dst:BrowsingNode {node_id: $target})
                MERGE (src)-[r:SIMILAR_TO]->(dst)
                SET r.weight = $weight, r.type = $type
            """, {
                "source": edge["source"],
                "target": edge["target"],
                "weight": edge["weight"],
                "type":   edge["type"],
            })

    print(f"Graph loaded: {len(nodes)} nodes, {len(edges)} edges.")

# ─── Graph traversal queries ───────────────────────────────────

def query_rabbit_hole(driver: Driver, session_id: str) -> list[dict]:
    """
    Return the full navigation chain for a session, ordered by depth.
    Used by: Rabbit Hole feature — Three.js path trace.
    """
    with driver.session() as session:
        result = session.run("""
            MATCH (n:BrowsingNode {session_id: $session_id})
            RETURN n.node_id AS id, n.title AS title, n.cluster AS cluster,
                   n.depth AS depth, n.is_distraction AS is_distraction,
                   n.time_spent AS time_spent, n.domain AS domain
            ORDER BY n.depth ASC
        """, {"session_id": session_id})
        return [dict(r) for r in result]


def query_referrer_chain(driver: Driver, node_id: str, max_hops: int = 5) -> list[dict]:
    """
    Trace back from a node through REFERRED_TO relationships.
    Used by: clicking a node in Three.js to see how you got there.
    """
    with driver.session() as session:
        result = session.run(f"""
            MATCH path = (origin:BrowsingNode)-[:REFERRED_TO*1..{max_hops}]->(target:BrowsingNode {{node_id: $node_id}})
            RETURN [n IN nodes(path) | {{
                id:    n.node_id,
                title: n.title,
                depth: n.depth,
                cluster: n.cluster
            }}] AS chain
            ORDER BY length(path) DESC
            LIMIT 1
        """, {"node_id": node_id})
        row = result.single()
        return row["chain"] if row else []


def query_cluster_graph(driver: Driver, cluster: str) -> dict:
    """
    All nodes and their semantic edges within a cluster.
    Used by: cluster zoom view in Three.js.
    """
    with driver.session() as session:
        node_result = session.run("""
            MATCH (n:BrowsingNode {cluster: $cluster})
            RETURN n.node_id AS id, n.title AS title, n.domain AS domain,
                   n.focus_score AS focus_score, n.days_since_visit AS days_since_visit
        """, {"cluster": cluster})
        nodes = [dict(r) for r in node_result]

        edge_result = session.run("""
            MATCH (a:BrowsingNode {cluster: $cluster})-[r:SIMILAR_TO]->(b:BrowsingNode {cluster: $cluster})
            RETURN a.node_id AS source, b.node_id AS target, r.weight AS weight
        """, {"cluster": cluster})
        edges = [dict(r) for r in edge_result]

        return {"cluster": cluster, "nodes": nodes, "edges": edges}


def query_escape_hatch_paths(driver: Driver) -> list[dict]:
    """
    For each escape node, find what focus chain preceded it in the same session.
    Used by: Escape Hatch feature.
    """
    with driver.session() as session:
        result = session.run("""
            MATCH (escape:BrowsingNode {is_escape_node: true})
            MATCH (focus:BrowsingNode {session_id: escape.session_id, is_distraction: false})
            WHERE focus.depth < escape.depth
            RETURN escape.node_id    AS escape_id,
                   escape.title      AS escape_title,
                   escape.session_id AS session_id,
                   collect({
                     id:    focus.node_id,
                     title: focus.title,
                     time:  focus.time_spent
                   }) AS focus_chain,
                   sum(focus.time_spent) AS focus_duration_seconds
            ORDER BY focus_duration_seconds DESC
        """)
        return [dict(r) for r in result]


def query_dead_stars(driver: Driver, threshold_days: int = 21) -> list[dict]:
    """
    Nodes not visited in threshold_days — visually dimmed in constellation.
    Used by: Dead Stars feature.
    """
    with driver.session() as session:
        result = session.run("""
            MATCH (n:BrowsingNode)
            WHERE n.days_since_visit >= $threshold
            RETURN n.node_id AS id, n.title AS title, n.cluster AS cluster,
                   n.days_since_visit AS days_since_visit, n.saved_for_later AS saved_for_later
            ORDER BY n.days_since_visit DESC
        """, {"threshold": threshold_days})
        return [dict(r) for r in result]


def query_similar_nodes(driver: Driver, node_id: str, top_k: int = 5) -> list[dict]:
    """
    Find the most similar nodes by SIMILAR_TO edge weight.
    Used by: Three.js hover — highlight neighbours.
    """
    with driver.session() as session:
        result = session.run("""
            MATCH (n:BrowsingNode {node_id: $node_id})-[r:SIMILAR_TO]->(m:BrowsingNode)
            RETURN m.node_id AS id, m.title AS title, m.cluster AS cluster, r.weight AS similarity
            ORDER BY r.weight DESC
            LIMIT $top_k
        """, {"node_id": node_id, "top_k": top_k})
        return [dict(r) for r in result]


def query_session_summary(driver: Driver) -> list[dict]:
    """
    Summary of all sessions: node count, total time, max depth, escape flag.
    Used by: session timeline view.
    """
    with driver.session() as session:
        result = session.run("""
            MATCH (n:BrowsingNode)-[:PART_OF]->(s:Session)
            RETURN s.session_id                AS session_id,
                   count(n)                    AS node_count,
                   sum(n.time_spent)           AS total_time,
                   max(n.depth)                AS max_depth,
                   sum(CASE WHEN n.is_escape_node THEN 1 ELSE 0 END) AS has_escape
            ORDER BY total_time DESC
        """)
        return [dict(r) for r in result]


# ─── Clear graph ───────────────────────────────────────────────

def clear_graph(driver: Driver) -> None:
    with driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")
    print("Graph cleared.")


# ─── Sample query runner ───────────────────────────────────────

def run_sample_queries(driver: Driver) -> None:
    print("\n--- Rabbit Hole: session_001 ---")
    chain = query_rabbit_hole(driver, "session_001")
    for node in chain:
        print(f"  depth={node['depth']} [{node['cluster']}] {node['title']}")

    print("\n--- Escape Hatch Paths ---")
    escapes = query_escape_hatch_paths(driver)
    for e in escapes[:3]:
        print(f"  {e['escape_title']} (focus before: {e['focus_duration_seconds']}s)")

    print("\n--- Dead Stars (21+ days) ---")
    dead = query_dead_stars(driver, threshold_days=21)
    for d in dead[:5]:
        print(f"  [{d['days_since_visit']}d] {d['title']}")

    print("\n--- Session Summary ---")
    sessions = query_session_summary(driver)
    for s in sessions[:5]:
        print(f"  {s['session_id']}: {s['node_count']} nodes, depth={s['max_depth']}, time={s['total_time']}s")

    print("\n--- Similar nodes to node_001 ---")
    similar = query_similar_nodes(driver, "node_001")
    for s in similar:
        print(f"  [{s['similarity']:.2f}] {s['title']}")


# ─── Entry point ───────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--clear",   action="store_true", help="Wipe graph before loading")
    parser.add_argument("--queries", action="store_true", help="Run sample graph queries after loading")
    args = parser.parse_args()

    driver = get_driver()

    if args.clear:
        clear_graph(driver)

    create_schema(driver)

    with open(MOCK_DATA_PATH) as f:
        data = json.load(f)

    load_graph(driver, data)

    if args.queries:
        run_sample_queries(driver)

    driver.close()
    print("\nDone. Open http://localhost:7474 to explore the graph.")
