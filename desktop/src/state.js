"use strict";
const fs = require("node:fs");

const DEFAULT = { width: 1280, height: 860 };

/** Remembers window size between launches. Corrupt or silly values fall back to the default. */
function loadWindowState(file) {
  try {
    const s = JSON.parse(fs.readFileSync(file, "utf8"));
    const ok = (n, lo, hi) => Number.isInteger(n) && n >= lo && n <= hi;
    if (ok(s.width, 800, 10000) && ok(s.height, 600, 10000)) return { width: s.width, height: s.height, maximized: s.maximized === true };
  } catch {
    /* first run or unreadable file */
  }
  return { ...DEFAULT, maximized: false };
}

function saveWindowState(file, state) {
  try {
    fs.writeFileSync(file, JSON.stringify({ width: state.width, height: state.height, maximized: !!state.maximized }));
  } catch {
    /* not worth interrupting the person */
  }
}

module.exports = { loadWindowState, saveWindowState, DEFAULT };
