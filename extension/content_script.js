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

  function metaContent(selector) {
    const el = document.querySelector(selector);
    return el && el.content ? el.content.trim() : null;
  }

  function extractPathTokens(pathname) {
    // /r/MachineLearning/comments/abc/understanding-transformers
    // → "MachineLearning comments understanding transformers"
    return pathname
      .split(/[/_\-]+/)
      .filter((t) => t.length > 2 && !/^\d+$/.test(t))
      .join(" ")
      .slice(0, 300);
  }

  function extractMainText() {
    // Prefer semantic content containers; fall back to body.
    // This skips nav/header/footer/aside on well-structured sites.
    const candidates = [
      "article",
      "main",
      "[role='main']",
      "#content",
      ".post-content",
      ".article-content",
    ];
    for (const sel of candidates) {
      const el = document.querySelector(sel);
      if (el && el.innerText && el.innerText.trim().length > 100) {
        return el.innerText;
      }
    }
    return document.body ? document.body.innerText || "" : "";
  }

  function clean(text) {
    return text.replace(/\s+/g, " ").trim();
  }

  function collect() {
    const title = document.title || "";

    // Structured metadata — usually clean and topic-rich
    const og_title =
      metaContent('meta[property="og:title"]') ||
      metaContent('meta[name="twitter:title"]');
    const og_description =
      metaContent('meta[property="og:description"]') ||
      metaContent('meta[name="twitter:description"]') ||
      metaContent('meta[name="description"]');
    const og_site_name = metaContent('meta[property="og:site_name"]');

    // First H1 — the page's own statement of its topic
    const h1El = document.querySelector("h1");
    const h1 = h1El && h1El.innerText ? clean(h1El.innerText).slice(0, 300) : null;

    // URL path tokens — slugs leak topic explicitly
    const path_tokens = extractPathTokens(window.location.pathname);

    // Main content (skips chrome), capped at 1500 chars (up from 500)
    const dom_snippet = clean(extractMainText()).slice(0, 1500);

    return {
      title,
      url: window.location.href,
      // Back-compat field; backend still reads this.
      description: og_description,
      dom_snippet,
      // New fields:
      og_title,
      og_description,
      og_site_name,
      h1,
      path_tokens,
    };
  }

  function send(reason) {
    try {
      const payload = collect();
      chrome.runtime.sendMessage(
        { type: "PAGE_CONTENT", reason, payload },
        () => {
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