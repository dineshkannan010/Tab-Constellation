// Tab Constellation — background service worker (MV3).
// State must survive SW restarts → use chrome.storage.* not module vars.

importScripts("logger.js");

const log = self.TCLog;
const API_BASE = "http://localhost:8000";
const APP_URL = "http://localhost:5173";

const QUEUE_KEY = "pending_queue";
const QUEUE_CAP = 200;
const SESSION_KEY = "session_id";
const HISTORY_FLAG = "history_backfilled";
const TAB_URL_MAP_KEY = "tab_url_map";
const COUNTER_TABS = "tabs_this_session";
const COUNTER_SCREENSHOT_TS = "last_screenshot_ts";
const ACTIVE_TAB_KEY = "active_tab";

const SCREENSHOT_ALARM = "screenshot_tick";
const RETRY_ALARM = "retry_tick";

// In-memory buffer of latest PAGE_CONTENT per tab_id (best-effort).
const latestContentByTab = new Map();
// Pending resolvers awaiting PAGE_CONTENT for tab_id.
const pendingContentWaiters = new Map();

// ------------------------- helpers -------------------------

function isoNow() {
  return new Date().toISOString();
}

function domainOf(url) {
  try {
    return new URL(url).hostname;
  } catch {
    return "";
  }
}

function isWebUrl(url) {
  return typeof url === "string" && (url.startsWith("http://") || url.startsWith("https://"));
}

async function getSessionId() {
  const got = await chrome.storage.session.get(SESSION_KEY);
  if (got[SESSION_KEY]) return got[SESSION_KEY];
  const id = crypto.randomUUID();
  await chrome.storage.session.set({ [SESSION_KEY]: id });
  log.info("new session", id);
  return id;
}

async function bumpCounter(key, delta = 1) {
  const got = await chrome.storage.local.get(key);
  const next = (got[key] || 0) + delta;
  await chrome.storage.local.set({ [key]: next });
  return next;
}

async function setLocal(obj) {
  await chrome.storage.local.set(obj);
}

async function getLocal(keys) {
  return chrome.storage.local.get(keys);
}

async function rememberTabUrl(tabId, url) {
  const got = await getLocal(TAB_URL_MAP_KEY);
  const map = got[TAB_URL_MAP_KEY] || {};
  map[String(tabId)] = url;
  await setLocal({ [TAB_URL_MAP_KEY]: map });
}

async function recallTabUrl(tabId) {
  const got = await getLocal(TAB_URL_MAP_KEY);
  const map = got[TAB_URL_MAP_KEY] || {};
  return map[String(tabId)] || null;
}

async function forgetTabUrl(tabId) {
  const got = await getLocal(TAB_URL_MAP_KEY);
  const map = got[TAB_URL_MAP_KEY] || {};
  delete map[String(tabId)];
  await setLocal({ [TAB_URL_MAP_KEY]: map });
}

// ------------------------- HTTP + queue -------------------------

async function post(endpoint, body) {
  const url = API_BASE + endpoint;
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      throw new Error("HTTP " + res.status);
    }
    return true;
  } catch (e) {
    log.warn("POST failed, queueing", endpoint, e.message);
    await enqueue(endpoint, body);
    return false;
  }
}

async function enqueue(endpoint, body) {
  const got = await getLocal(QUEUE_KEY);
  const q = got[QUEUE_KEY] || [];
  q.push({ endpoint, body, queued_at: isoNow() });
  while (q.length > QUEUE_CAP) q.shift();
  await setLocal({ [QUEUE_KEY]: q });
}

async function flushQueue() {
  const got = await getLocal(QUEUE_KEY);
  const q = got[QUEUE_KEY] || [];
  if (q.length === 0) return;
  log.info("flushing queue, size:", q.length);
  const remaining = [];
  for (const item of q) {
    try {
      const res = await fetch(API_BASE + item.endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(item.body),
      });
      if (!res.ok) remaining.push(item);
    } catch {
      remaining.push(item);
    }
  }
  await setLocal({ [QUEUE_KEY]: remaining });
  log.info("flush done, remaining:", remaining.length);
}

// ------------------------- content waiters -------------------------

function waitForContent(tabId, timeoutMs = 3000) {
  const cached = latestContentByTab.get(tabId);
  if (cached && Date.now() - cached.receivedAt < 5000) {
    return Promise.resolve(cached.payload);
  }
  return new Promise((resolve) => {
    let done = false;
    const t = setTimeout(() => {
      if (done) return;
      done = true;
      const arr = pendingContentWaiters.get(tabId) || [];
      pendingContentWaiters.set(
        tabId,
        arr.filter((x) => x.resolve !== resolve)
      );
      resolve(null);
    }, timeoutMs);
    const entry = {
      resolve: (payload) => {
        if (done) return;
        done = true;
        clearTimeout(t);
        resolve(payload);
      },
    };
    const arr = pendingContentWaiters.get(tabId) || [];
    arr.push(entry);
    pendingContentWaiters.set(tabId, arr);
  });
}

chrome.runtime.onMessage.addListener((msg, sender) => {
  if (!msg || msg.type !== "PAGE_CONTENT") return;
  const tabId = sender.tab && sender.tab.id;
  if (typeof tabId !== "number") return;
  if (sender.tab && sender.tab.incognito) return; // never buffer incognito content
  latestContentByTab.set(tabId, { payload: msg.payload, receivedAt: Date.now() });
  const waiters = pendingContentWaiters.get(tabId) || [];
  for (const w of waiters) w.resolve(msg.payload);
  pendingContentWaiters.set(tabId, []);
});

// ------------------------- tab events -------------------------

chrome.tabs.onCreated.addListener(async (tab) => {
  if (tab.incognito) return;
  try {
    const session_id = await getSessionId();
    await post("/ingest/event", {
      tab_id: tab.id,
      window_id: tab.windowId,
      session_id,
      event_type: "tab_created",
      timestamp: isoNow(),
      url: null,
    });
  } catch (e) {
    log.error("onCreated handler", e);
  }
});

chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
  if (changeInfo.status !== "complete") return;
  if (tab.incognito) return;
  if (!isWebUrl(tab.url)) return;

  try {
    await rememberTabUrl(tabId, tab.url);
    const session_id = await getSessionId();

    const content = await waitForContent(tabId, 3000);
    const title = (content && content.title) || tab.title || "";
    const meta_description = content ? content.description : null;
    const dom_snippet = content ? content.dom_snippet : "";

    const sent = await post("/ingest/tab", {
      tab_id: tabId,
      window_id: tab.windowId,
      opener_tab_id: typeof tab.openerTabId === "number" ? tab.openerTabId : null,
      session_id,
      url: tab.url,
      domain: domainOf(tab.url),
      title,
      meta_description,
      dom_snippet,
      // New extraction fields — pass through to backend
      og_title: content ? content.og_title : null,
      og_description: content ? content.og_description : null,
      og_site_name: content ? content.og_site_name : null,
      h1: content ? content.h1 : null,
      path_tokens: content ? content.path_tokens : "",
      timestamp: isoNow(),
      event_type: "tab_loaded",
    });
    if (sent) await bumpCounter(COUNTER_TABS, 1);
  } catch (e) {
    log.error("onUpdated handler", e);
  }
});

chrome.tabs.onActivated.addListener(async ({ tabId, windowId }) => {
  try {
    let tab;
    try {
      tab = await chrome.tabs.get(tabId);
    } catch {
      tab = null;
    }
    if (tab && tab.incognito) return;
    const session_id = await getSessionId();
    const url = await recallTabUrl(tabId);
    await setLocal({ [ACTIVE_TAB_KEY]: { tabId, windowId, since: isoNow() } });
    await post("/ingest/event", {
      tab_id: tabId,
      window_id: windowId,
      session_id,
      event_type: "tab_activated",
      timestamp: isoNow(),
      url,
    });
  } catch (e) {
    log.error("onActivated handler", e);
  }
});

chrome.tabs.onRemoved.addListener(async (tabId, removeInfo) => {
  try {
    const session_id = await getSessionId();
    const url = await recallTabUrl(tabId);
    await post("/ingest/event", {
      tab_id: tabId,
      window_id: removeInfo.windowId,
      session_id,
      event_type: "tab_closed",
      timestamp: isoNow(),
      url,
    });
    await forgetTabUrl(tabId);
    latestContentByTab.delete(tabId);
  } catch (e) {
    log.error("onRemoved handler", e);
  }
});

// ------------------------- screenshots -------------------------

async function captureScreenshotTick() {
  try {
    const win = await chrome.windows.getLastFocused({ populate: false });
    if (!win || !win.focused || win.incognito) return;
    const tabs = await chrome.tabs.query({ active: true, windowId: win.id });
    const tab = tabs && tabs[0];
    if (!tab || tab.incognito || !isWebUrl(tab.url)) return;

    let dataUrl;
    try {
      dataUrl = await chrome.tabs.captureVisibleTab(win.id, { format: "jpeg", quality: 50 });
    } catch (e) {
      // captureVisibleTab throws on chrome:// pages, PDFs, unfocused windows, etc.
      log.info("screenshot skip:", e.message);
      return;
    }
    if (!dataUrl) return;
    const b64 = dataUrl.replace(/^data:image\/jpeg;base64,/, "");

    const session_id = await getSessionId();
    const sent = await post("/ingest/screenshot", {
      tab_id: tab.id,
      window_id: tab.windowId,
      session_id,
      url: tab.url,
      screenshot_b64: b64,
      timestamp: isoNow(),
    });
    if (sent) await setLocal({ [COUNTER_SCREENSHOT_TS]: Date.now() });
  } catch (e) {
    log.error("screenshot tick", e);
  }
}

// ------------------------- history backfill -------------------------

async function runHistoryBackfill() {
  try {
    log.info("history backfill starting");
    const session_id = await getSessionId();
    const startTime = Date.now() - 30 * 24 * 60 * 60 * 1000;
    const items = await chrome.history.search({ text: "", startTime, maxResults: 5000 });
    log.info("history rows:", items.length);

    const batchSize = 50;
    for (let i = 0; i < items.length; i += batchSize) {
      const slice = items.slice(i, i + batchSize).map((h) => ({
        url: h.url || "",
        title: h.title || "",
        last_visit_time: h.lastVisitTime ? new Date(h.lastVisitTime).toISOString() : isoNow(),
        visit_count: h.visitCount || 0,
        typed_count: h.typedCount || 0,
        domain: domainOf(h.url || ""),
      }));
      await post("/ingest/history-batch", { session_id, items: slice });
      await new Promise((r) => setTimeout(r, 500));
    }

    await setLocal({ [HISTORY_FLAG]: true });
    log.info("history backfill done");
  } catch (e) {
    log.error("backfill failed", e);
  }
}

// ------------------------- alarms / lifecycle -------------------------

chrome.runtime.onInstalled.addListener(async (details) => {
  log.info("onInstalled", details.reason);
  chrome.alarms.create(SCREENSHOT_ALARM, { periodInMinutes: 0.5 });
  chrome.alarms.create(RETRY_ALARM, { periodInMinutes: 1 });
  if (details.reason === "install") {
    const got = await getLocal(HISTORY_FLAG);
    if (!got[HISTORY_FLAG]) runHistoryBackfill();
  }
});

chrome.runtime.onStartup.addListener(() => {
  log.info("onStartup");
  chrome.alarms.create(SCREENSHOT_ALARM, { periodInMinutes: 0.5 });
  chrome.alarms.create(RETRY_ALARM, { periodInMinutes: 1 });
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === SCREENSHOT_ALARM) captureScreenshotTick();
  else if (alarm.name === RETRY_ALARM) flushQueue();
});

// ------------------------- popup messages -------------------------

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (!msg || !msg.type) return;
  if (msg.type === "POPUP_GET_STATE") {
    (async () => {
      const session_id = await getSessionId();
      const got = await getLocal([
        QUEUE_KEY,
        COUNTER_TABS,
        COUNTER_SCREENSHOT_TS,
        HISTORY_FLAG,
      ]);
      let health = false;
      try {
        const r = await fetch(API_BASE + "/health");
        health = r.ok;
      } catch {
        health = false;
      }
      sendResponse({
        session_id,
        tabs_this_session: got[COUNTER_TABS] || 0,
        pending_queue_size: (got[QUEUE_KEY] || []).length,
        last_screenshot_ts: got[COUNTER_SCREENSHOT_TS] || null,
        history_backfilled: !!got[HISTORY_FLAG],
        backend_ok: health,
      });
    })();
    return true; // async response
  }
  if (msg.type === "POPUP_OPEN_APP") {
    chrome.tabs.create({ url: APP_URL });
    sendResponse({ ok: true });
    return false;
  }
  if (msg.type === "POPUP_RERUN_BACKFILL") {
    (async () => {
      await chrome.storage.local.remove(HISTORY_FLAG);
      runHistoryBackfill();
      sendResponse({ ok: true });
    })();
    return true;
  }
  if (msg.type === "POPUP_FLUSH_QUEUE") {
    (async () => {
      await flushQueue();
      sendResponse({ ok: true });
    })();
    return true;
  }
  if (msg.type === "POPUP_CLEAR_STATE") {
    (async () => {
      await chrome.storage.local.clear();
      await chrome.storage.session.clear();
      latestContentByTab.clear();
      pendingContentWaiters.clear();
      sendResponse({ ok: true });
    })();
    return true;
  }
});

log.info("background loaded");