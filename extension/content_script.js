(function () {
  const log = self.TCLog || console;

  const url = window.location.href;
  if (
    url.startsWith("chrome://") ||
    url.startsWith("chrome-extension://") ||
    url.startsWith("about:")
  ) {
    return;
  }

  function collect() {
    const title = document.title || "";
    const descEl = document.querySelector('meta[name="description"]');
    const description = descEl && descEl.content ? descEl.content : null;
    const raw = document.body ? document.body.innerText || "" : "";
    const dom_snippet = raw.replace(/\s+/g, " ").trim().slice(0, 500);
    return {
      title,
      url: window.location.href,
      description,
      dom_snippet,
    };
  }

  function send(reason) {
    try {
      const payload = collect();
      chrome.runtime.sendMessage(
        { type: "PAGE_CONTENT", reason, payload },
        () => {
          // Swallow lastError — SW may be asleep between hops.
          void chrome.runtime.lastError;
        }
      );
    } catch (e) {
      log.warn && log.warn("content_script send failed:", e);
    }
  }

  send("load");

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") {
      send("visibilitychange");
    }
  });
})();