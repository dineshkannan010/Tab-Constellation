(function () {
  const $ = (id) => document.getElementById(id);

  function ageString(ts) {
    if (!ts) return "—";
    const s = Math.max(0, Math.floor((Date.now() - ts) / 1000));
    if (s < 60) return s + "s ago";
    const m = Math.floor(s / 60);
    if (m < 60) return m + "m ago";
    const h = Math.floor(m / 60);
    return h + "h ago";
  }

  function send(type) {
    return new Promise((resolve) => {
      chrome.runtime.sendMessage({ type }, (resp) => {
        void chrome.runtime.lastError;
        resolve(resp);
      });
    });
  }

  function setFooter(msg) {
    $("footer").textContent = msg || "";
  }

  async function refresh() {
    const s = await send("POPUP_GET_STATE");
    if (!s) {
      setFooter("Background not responding");
      return;
    }
    $("session").textContent = s.session_id ? s.session_id.slice(0, 8) : "—";
    $("tabs").textContent = String(s.tabs_this_session || 0);
    $("pending").textContent = String(s.pending_queue_size || 0);
    $("last-shot").textContent = ageString(s.last_screenshot_ts);
    // $("backfilled").textContent = s.history_backfilled ? "done" : "not yet";

    const dot = $("health-dot");
    const label = $("health-label");
    if (s.backend_ok) {
      dot.classList.add("ok");
      dot.classList.remove("err");
      label.textContent = "backend ok";
    } else {
      dot.classList.add("err");
      dot.classList.remove("ok");
      label.textContent = "backend down";
    }
  }

  $("btn-open").addEventListener("click", async () => {
    await send("POPUP_OPEN_APP");
    window.close();
  });

  // $("btn-backfill").addEventListener("click", async () => {
  //   setFooter("Backfill kicked off…");
  //   await send("POPUP_RERUN_BACKFILL");
  //   setTimeout(refresh, 500);
  // });

  $("btn-flush").addEventListener("click", async () => {
    setFooter("Flushing queue…");
    await send("POPUP_FLUSH_QUEUE");
    setFooter("Flush done.");
    refresh();
  });

  $("btn-clear").addEventListener("click", async () => {
    if (!confirm("Clear all local extension state? This wipes counters, queue, and session id.")) return;
    await send("POPUP_CLEAR_STATE");
    setFooter("Local state cleared.");
    refresh();
  });

  refresh();
  setInterval(refresh, 20000);
})();