(function (root) {
  const PREFIX = "TC:";

  function fmt(level, args) {
    return ["%c" + PREFIX + " " + level.toUpperCase(), "color:#7dd3fc;font-weight:600", ...args];
  }

  const logger = {
    info(...args) {
      console.log(...fmt("info", args));
    },
    warn(...args) {
      console.warn(...fmt("warn", args));
    },
    error(...args) {
      console.error(...fmt("error", args));
    },
  };

  root.TCLog = logger;
})(typeof self !== "undefined" ? self : globalThis);