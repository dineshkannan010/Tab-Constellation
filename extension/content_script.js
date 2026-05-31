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
    return pathname
      .split(/[/_\-]+/)
      .filter((t) => t.length > 2 && !/^\d+$/.test(t))
      .join(" ")
      .slice(0, 300);
  }

  function extractMainText() {
    const candidates = [
      "article", "main", "[role='main']",
      "#content", ".post-content", ".article-content",
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

    // Structured metadata
    const og_title =
      metaContent('meta[property="og:title"]') ||
      metaContent('meta[name="twitter:title"]');
    const og_description =
      metaContent('meta[property="og:description"]') ||
      metaContent('meta[name="twitter:description"]') ||
      metaContent('meta[name="description"]');
    const og_site_name = metaContent('meta[property="og:site_name"]');

    const h1El = document.querySelector("h1");
    const h1 = h1El && h1El.innerText
      ? clean(h1El.innerText).slice(0, 300) : null;

    const path_tokens = extractPathTokens(window.location.pathname);
    const dom_snippet = clean(extractMainText()).slice(0, 1500);

    // ── YouTube enrichment ──────────────────────────────────
    let youtube_data = null;
    if (window.location.hostname.includes("youtube.com")) {
      const videoTitle = document.querySelector(
        'h1.ytd-video-primary-info-renderer, h1.style-scope.ytd-watch-metadata'
      )?.textContent?.trim();

      const channel = document.querySelector(
        '#channel-name a, ytd-channel-name a'
      )?.textContent?.trim();

      const videoDesc = document.querySelector(
        '#description-text, ytd-text-inline-expander'
      )?.textContent?.trim()?.slice(0, 200);

      const category = document.querySelector(
        'meta[itemprop="genre"]'
      )?.getAttribute("content");

      if (videoTitle || channel) {
        youtube_data = {
          video_title: videoTitle,
          channel,
          video_description: videoDesc,
          category,
        };
      }
    }

    return {
      title,
      url: window.location.href,
      description: og_description,
      dom_snippet,
      og_title,
      og_description,
      og_site_name,
      h1,
      path_tokens,
      youtube_data,
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

  // Timing strategy per domain
  if (window.location.hostname.includes("reddit.com")) {
    // Reddit is SPA — wait for content to load
    setTimeout(() => send("load_delayed"), 2000);
  } else if (window.location.hostname.includes("youtube.com")) {
    // YouTube: send immediately (page title) + delayed (video title)
    send("load");
    setTimeout(() => send("load_delayed"), 3000);
  } else {
    send("load");
  }

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") {
      send("visibilitychange");
    }
  });
})();