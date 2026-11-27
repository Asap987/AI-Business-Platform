"use strict";
const path = require("node:path");
const fs = require("node:fs");
const { app, BrowserWindow, Menu, shell, session, dialog } = require("electron");
const { resolveAppOrigin, allowNavigation, allowExternalOpen, allowPermission } = require("./security");
const { loadWindowState, saveWindowState } = require("./state");

const PARTITION = "persist:kasora"; // sign-in cookies live here, separate from any other app
let win = null;
let origin = null;
let appUrl = null;

function configuredUrl() {
  if (process.env.KASORA_APP_URL) return process.env.KASORA_APP_URL;
  const candidates = [path.join(process.resourcesPath || "", "app-config.json"), path.join(__dirname, "..", "app-config.json")];
  for (const file of candidates) {
    try {
      const url = JSON.parse(fs.readFileSync(file, "utf8")).appUrl;
      if (url) return url;
    } catch {
      /* try the next place */
    }
  }
  return "";
}

function createWindow() {
  const stateFile = path.join(app.getPath("userData"), "window-state.json");
  const state = loadWindowState(stateFile);
  win = new BrowserWindow({
    width: state.width, height: state.height, minWidth: 900, minHeight: 600, show: false, backgroundColor: "#0f172a", title: "KASORA AI",
    webPreferences: {
      partition: PARTITION, preload: path.join(__dirname, "preload.js"),
      contextIsolation: true, nodeIntegration: false, sandbox: true, webSecurity: true,
      allowRunningInsecureContent: false, webviewTag: false, devTools: !app.isPackaged,
    },
  });
  if (state.maximized) win.maximize();
  win.once("ready-to-show", () => win.show());

  const persist = () => {
    if (!win || win.isDestroyed()) return;
    const b = win.getNormalBounds();
    saveWindowState(stateFile, { width: b.width, height: b.height, maximized: win.isMaximized() });
  };
  win.on("close", persist);

  win.webContents.on("did-fail-load", (_e, code, description, _failedUrl, isMainFrame) => {
    if (!isMainFrame || code === -3) return; // -3 = aborted by a redirect we caused
    win.loadFile(path.join(__dirname, "offline.html"), { query: { reason: `${description} (${code})` } });
  });
  load();
}

function load() {
  if (win && !win.isDestroyed()) win.loadURL(appUrl);
}

/** Applied to EVERY window and frame host, including popups the app opens, so no window can be steered off the app's origin. */
function guardContents(contents) {
  contents.on("will-navigate", (event, url) => {
    if (url.startsWith("kasora-retry://")) { event.preventDefault(); load(); return; }
    if (!allowNavigation(url, origin)) {
      event.preventDefault();
      if (allowExternalOpen(url)) shell.openExternal(url);
    }
  });
  contents.on("will-redirect", (event, url) => { if (!allowNavigation(url, origin) && !url.startsWith("file:")) event.preventDefault(); });
  contents.setWindowOpenHandler(({ url }) => {
    if (allowNavigation(url, origin)) return { action: "allow" };
    if (allowExternalOpen(url)) shell.openExternal(url);
    return { action: "deny" };
  });
  contents.on("will-attach-webview", (event) => event.preventDefault());
}

function lockDownSession() {
  const ses = session.fromPartition(PARTITION);
  ses.setPermissionRequestHandler((wc, permission, callback, details) => callback(allowPermission(permission, details.requestingUrl || wc.getURL(), origin, details)));
  ses.setPermissionCheckHandler((wc, permission, requestingOrigin, details) => allowPermission(permission, requestingOrigin, origin, { mediaTypes: details.mediaType === "audio" ? ["audio"] : [] }));
  // Never silently accept a bad certificate.
  ses.setCertificateVerifyProc((request, callback) => callback(-3));
  ses.setDevicePermissionHandler(() => false);
}

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on("second-instance", () => { if (win) { if (win.isMinimized()) win.restore(); win.focus(); } });
  app.whenReady().then(() => {
    try {
      origin = resolveAppOrigin(configuredUrl(), { packaged: app.isPackaged });
      appUrl = origin + "/";
    } catch (err) {
      dialog.showErrorBox("KASORA AI can't start", `${err.message}\n\nAsk your administrator for the correct installer.`);
      app.quit();
      return;
    }
    Menu.setApplicationMenu(Menu.buildFromTemplate([
      ...(process.platform === "darwin" ? [{ role: "appMenu" }] : []),
      { role: "editMenu" },
      { label: "View", submenu: [{ role: "reload" }, { role: "togglefullscreen" }, { role: "resetZoom" }, { role: "zoomIn" }, { role: "zoomOut" }] },
      { role: "windowMenu" },
    ]));
    app.on("web-contents-created", (_event, contents) => guardContents(contents));
    lockDownSession();
    createWindow();
    app.on("activate", () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });
  });
  app.on("window-all-closed", () => { if (process.platform !== "darwin") app.quit(); });
}
