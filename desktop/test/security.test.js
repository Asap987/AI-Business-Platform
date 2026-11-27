"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const { resolveAppOrigin, allowNavigation, allowExternalOpen, allowPermission } = require("../src/security");
const { loadWindowState, saveWindowState } = require("../src/state");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

test("packaged builds accept https only", () => {
  assert.equal(resolveAppOrigin("https://app.kasora.example/dashboard", { packaged: true }), "https://app.kasora.example");
  for (const bad of ["http://app.kasora.example", "http://localhost:3000", "ftp://x.y", "javascript:alert(1)", "", undefined, "not a url", "https://user:pw@app.example"]) {
    assert.throws(() => resolveAppOrigin(bad, { packaged: true }), undefined, String(bad));
  }
});

test("development allows http only for localhost", () => {
  assert.equal(resolveAppOrigin("http://localhost:3000", { packaged: false }), "http://localhost:3000");
  assert.equal(resolveAppOrigin("http://127.0.0.1:3000", { packaged: false }), "http://127.0.0.1:3000");
  assert.throws(() => resolveAppOrigin("http://app.kasora.example", { packaged: false }));
  assert.throws(() => resolveAppOrigin("http://localhost.evil.example", { packaged: false }));
});

const ORIGIN = "https://app.kasora.example";

test("navigation stays on the app's own origin", () => {
  assert.ok(allowNavigation("https://app.kasora.example/cases", ORIGIN));
  for (const url of ["https://app.kasora.example.evil.test/", "http://app.kasora.example/", "https://evil.test/", "https://app.kasora.example:8443/", "file:///etc/passwd", "data:text/html,hi", "javascript:1", "garbage"]) {
    assert.equal(allowNavigation(url, ORIGIN), false, url);
  }
});

test("only plain https links go to the system browser", () => {
  assert.ok(allowExternalOpen("https://example.com/help"));
  for (const url of ["http://example.com", "file:///C:/Windows/System32/calc.exe", "smb://host/share", "ms-msdt:/id", "javascript:1", "https://u:p@example.com", "x"]) {
    assert.equal(allowExternalOpen(url), false, url);
  }
});

test("only the microphone, only for the app, is allowed", () => {
  const mic = { mediaTypes: ["audio"] };
  assert.ok(allowPermission("media", "https://app.kasora.example/voice", ORIGIN, mic));
  assert.equal(allowPermission("media", "https://evil.test/", ORIGIN, mic), false);
  assert.equal(allowPermission("media", "https://app.kasora.example/", ORIGIN, { mediaTypes: ["audio", "video"] }), false);
  assert.equal(allowPermission("media", "https://app.kasora.example/", ORIGIN, { mediaTypes: ["video"] }), false);
  assert.equal(allowPermission("media", "https://app.kasora.example/", ORIGIN, {}), false);
  for (const p of ["geolocation", "notifications", "camera", "clipboard-read", "openExternal", "midi", "display-capture", "fullscreen"]) {
    assert.equal(allowPermission(p, "https://app.kasora.example/", ORIGIN, mic), false, p);
  }
});

test("window state survives a restart and ignores junk", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "kasora-"));
  const file = path.join(dir, "s.json");
  assert.deepEqual(loadWindowState(file), { width: 1280, height: 860, maximized: false });
  saveWindowState(file, { width: 1000, height: 700, maximized: true });
  assert.deepEqual(loadWindowState(file), { width: 1000, height: 700, maximized: true });
  for (const junk of ['{"width":1,"height":1}', '{"width":"big"}', "not json", '{"width":99999,"height":700}']) {
    fs.writeFileSync(file, junk);
    assert.deepEqual(loadWindowState(file), { width: 1280, height: 860, maximized: false }, junk);
  }
});
