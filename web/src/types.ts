// ============================================================
// Tab Constellation — TypeScript Types + Mock Data Loader
// API Contract v1.0  (you define this, teammate 1 adapts)
// ============================================================

// ─── Core node type ─────────────────────────────────────────

export interface ConstellationNode {
  // Identity
  id: string;
  url: string;
  title: string;
  domain: string;

  // Temporal
  visitedAt: string;          // ISO 8601 — first visit in this record
  lastVisitedAt: string;      // ISO 8601 — most recent visit
  daysSinceVisit: number;     // computed from lastVisitedAt vs now

  // Engagement
  visitCount: number;
  timeSpent: number;          // seconds
  scrollDepth: number;        // 0–1
  lastScrollPosition: number; // 0–1

  // Navigation graph
  referrer: string | null;    // node_id that led here (null = direct)
  depth: number;              // hops from session origin (0 = direct)
  sessionId: string;

  // Semantic
  cluster: string;            // e.g. "ai-research", "social"
  embedding: number[];        // raw vector — Three.js computes position from this

  // Feature flags
  isDistraction: boolean;     // drives Distraction Fingerprint
  focusScore: number;         // 0–1, drives Focus Score Gauge
  tabClosedWithoutReturn: boolean; // drives Unresolved Loops
  savedForLater: boolean;     // drives Guilt Pile
  revisited: boolean;         // true if returned to after closing
  isEscapeNode: boolean;      // first node opened after a deep focus session
}

// ─── Edge between nodes ──────────────────────────────────────

export interface ConstellationEdge {
  source: string;             // node_id
  target: string;             // node_id
  weight: number;             // 0–1 cosine similarity (or navigation strength)
  type: "semantic" | "navigation";
}

// ─── Top-level API response ───────────────────────────────────

export interface ConstellationResponse {
  nodes: ConstellationNode[];
  edges: ConstellationEdge[];
  meta: {
    generatedAt: string;
    totalNodes: number;
    totalEdges: number;
    clusters: string[];
    sessions: string[];
  };
}

// ─── Feature-derived types (computed in your frontend) ────────

/**
 * Focus Score Gauge
 * Aggregate focusScore across a time window.
 */
export interface FocusGaugeData {
  score: number;              // 0–1
  distractionRatio: number;   // % of nodes with isDistraction=true
  deepFocusMinutes: number;   // total timeSpent on non-distraction nodes / 60
}

/**
 * Distraction Fingerprint
 * What domains / clusters pull the user away and when.
 */
export interface DistractionFingerprint {
  topDistractionDomains: { domain: string; count: number; totalTime: number }[];
  timeOfDayHeatmap: number[];  // 24 values, each = distraction minutes in that hour
  worstCluster: string;
}

/**
 * Unresolved Loops
 * Pages closed without being finished — the "open tabs guilt."
 */
export interface UnresolvedLoop {
  nodeId: string;
  title: string;
  url: string;
  scrollDepth: number;        // how far they got
  daysSinceVisit: number;
}

/**
 * Rabbit Hole
 * A chain of nodes where depth keeps increasing within a session.
 */
export interface RabbitHole {
  sessionId: string;
  chain: string[];            // ordered node_ids from depth 0 → N
  maxDepth: number;
  totalTimeSpent: number;     // seconds across the chain
  originCluster: string;
  exitCluster: string;        // where they landed (often social/entertainment)
}

/**
 * Guilt Pile
 * savedForLater=true but not revisited, sorted by staleness.
 */
export interface GuiltItem {
  nodeId: string;
  title: string;
  url: string;
  daysSinceVisit: number;
  cluster: string;
}

/**
 * Escape Hatch
 * The node that broke a focus session — entry point to distraction.
 */
export interface EscapeHatch {
  nodeId: string;
  title: string;
  domain: string;
  sessionId: string;
  focusSessionDuration: number; // seconds of focus before escape
}

/**
 * Dead Stars
 * Nodes not visited for a long time — still in the constellation but cold.
 */
export interface DeadStar {
  nodeId: string;
  title: string;
  url: string;
  cluster: string;
  daysSinceVisit: number;
  savedForLater: boolean;
}

// ─── Qdrant payload shape ─────────────────────────────────────
// This is what gets stored per point in Qdrant alongside the vector.
// Keep it flat — no nested objects — for efficient payload filtering.

export interface QdrantPayload {
  node_id: string;
  url: string;
  title: string;
  domain: string;
  visited_at: string;
  last_visited_at: string;
  days_since_visit: number;
  visit_count: number;
  time_spent: number;
  scroll_depth: number;
  tab_closed_without_return: boolean;
  referrer: string | null;
  depth: number;
  session_id: string;
  cluster: string;
  is_distraction: boolean;
  focus_score: number;
  saved_for_later: boolean;
  revisited: boolean;
  is_escape_node: boolean;
}

// ─── Mock data loader ─────────────────────────────────────────

import mockDataRaw from "./mockData.json";

export const mockData: ConstellationResponse =
  mockDataRaw as ConstellationResponse;

// ─── Feature helpers (pure, no side effects) ──────────────────

export function computeFocusGauge(nodes: ConstellationNode[]): FocusGaugeData {
  if (!nodes.length) return { score: 0, distractionRatio: 0, deepFocusMinutes: 0 };
  const avg = nodes.reduce((s, n) => s + n.focusScore, 0) / nodes.length;
  const distractions = nodes.filter((n) => n.isDistraction);
  const focusTime = nodes
    .filter((n) => !n.isDistraction)
    .reduce((s, n) => s + n.timeSpent, 0);
  return {
    score: avg,
    distractionRatio: distractions.length / nodes.length,
    deepFocusMinutes: Math.round(focusTime / 60),
  };
}

export function getUnresolvedLoops(nodes: ConstellationNode[]): UnresolvedLoop[] {
  return nodes
    .filter((n) => n.tabClosedWithoutReturn && n.scrollDepth < 0.9)
    .map((n) => ({
      nodeId: n.id,
      title: n.title,
      url: n.url,
      scrollDepth: n.scrollDepth,
      daysSinceVisit: n.daysSinceVisit,
    }))
    .sort((a, b) => b.daysSinceVisit - a.daysSinceVisit);
}

export function getGuiltPile(nodes: ConstellationNode[]): GuiltItem[] {
  return nodes
    .filter((n) => n.savedForLater && !n.revisited)
    .map((n) => ({
      nodeId: n.id,
      title: n.title,
      url: n.url,
      daysSinceVisit: n.daysSinceVisit,
      cluster: n.cluster,
    }))
    .sort((a, b) => b.daysSinceVisit - a.daysSinceVisit);
}

export function getDeadStars(
  nodes: ConstellationNode[],
  thresholdDays = 21
): DeadStar[] {
  return nodes
    .filter((n) => n.daysSinceVisit >= thresholdDays)
    .map((n) => ({
      nodeId: n.id,
      title: n.title,
      url: n.url,
      cluster: n.cluster,
      daysSinceVisit: n.daysSinceVisit,
      savedForLater: n.savedForLater,
    }))
    .sort((a, b) => b.daysSinceVisit - a.daysSinceVisit);
}

export function getEscapeHatches(nodes: ConstellationNode[]): EscapeHatch[] {
  // Group by session, find the isEscapeNode per session
  const sessionMap = new Map<string, ConstellationNode[]>();
  nodes.forEach((n) => {
    if (!sessionMap.has(n.sessionId)) sessionMap.set(n.sessionId, []);
    sessionMap.get(n.sessionId)!.push(n);
  });

  const result: EscapeHatch[] = [];
  sessionMap.forEach((sessionNodes, sessionId) => {
    const sorted = [...sessionNodes].sort(
      (a, b) => new Date(a.visitedAt).getTime() - new Date(b.visitedAt).getTime()
    );
    const escapeIdx = sorted.findIndex((n) => n.isEscapeNode);
    if (escapeIdx === -1) return;
    const beforeEscape = sorted.slice(0, escapeIdx);
    const focusTime = beforeEscape.reduce((s, n) => s + n.timeSpent, 0);
    const escape = sorted[escapeIdx];
    result.push({
      nodeId: escape.id,
      title: escape.title,
      domain: escape.domain,
      sessionId,
      focusSessionDuration: focusTime,
    });
  });
  return result.sort((a, b) => b.focusSessionDuration - a.focusSessionDuration);
}

export function getRabbitHoles(
  nodes: ConstellationNode[],
  minDepth = 2
): RabbitHole[] {
  const sessionMap = new Map<string, ConstellationNode[]>();
  nodes.forEach((n) => {
    if (!sessionMap.has(n.sessionId)) sessionMap.set(n.sessionId, []);
    sessionMap.get(n.sessionId)!.push(n);
  });

  const result: RabbitHole[] = [];
  sessionMap.forEach((sessionNodes, sessionId) => {
    const maxDepth = Math.max(...sessionNodes.map((n) => n.depth));
    if (maxDepth < minDepth) return;
    const sorted = [...sessionNodes].sort((a, b) => a.depth - b.depth);
    const origin = sorted.find((n) => n.depth === 0);
    const deepest = sorted.find((n) => n.depth === maxDepth);
    result.push({
      sessionId,
      chain: sorted.map((n) => n.id),
      maxDepth,
      totalTimeSpent: sorted.reduce((s, n) => s + n.timeSpent, 0),
      originCluster: origin?.cluster ?? "unknown",
      exitCluster: deepest?.cluster ?? "unknown",
    });
  });
  return result.sort((a, b) => b.maxDepth - a.maxDepth);
}
