# KASORA AI desktop app (Windows and macOS) — status

Folder: `desktop/`. Added 2026-11-27. It is a **thin, locked-down window around the web app** (Electron), not a second copy of the product.

## Design decisions
- The web app and the backend stay the single source of truth: accounts, permissions, tenant isolation, the privacy gate and every provider key remain **server-side**. The desktop app holds no API keys, no database, no business data except the browser-style sign-in cookie kept in its own storage.
- Updates to the product reach desktop users immediately because the window loads the deployed web app. The installer only changes when the shell itself changes.
- Sign-in cookies live in a separate persistent store (`persist:kasora`). The backend must therefore allow the app's origin exactly as it does for the browser (cookies, CORS/Origin checks). Nothing was changed in the backend for this.

## Security rules (all in `desktop/src/security.js`, unit-tested, and checked in a real Electron window under a virtual display)
- Packaged builds load **https only**; `http` is accepted only for `localhost` in development; no user name or password in the address.
- The page gets no Node, no `require`, no Electron objects (context isolation, sandbox, empty preload).
- Navigation and popups are limited to the app's own origin, in **every** window (a gap found and fixed during testing: popups first escaped the guard). Other sites open in the normal browser, `https` only. `file:`, `smb:`, `ms-msdt:` and similar links are refused.
- Permissions: only the **microphone**, only for the app's own pages (test calls). Camera, location, notifications, clipboard, devices are refused. Verified: microphone granted; camera, location and notifications denied.
- Bad certificates are never accepted. Developer tools are off in packaged builds. One window instance at a time. No telemetry, no auto-updater.
- If the app cannot be reached, a local offline page with "Try again" is shown.

## Build and run
```
cd desktop
npm install
KASORA_APP_URL=http://localhost:3000 npm start     # development, against the local web app
npm test                                          # 6 unit tests, no display needed
```
Installers: set `appUrl` in `desktop/app-config.json` (https only) or use the manual GitHub Actions workflow **Desktop installers** (`.github/workflows/desktop.yml`), which builds `.exe` (Windows, NSIS) and `.dmg` (macOS) as downloadable artifacts. Nothing is published automatically.

## Verified, and not verified
- Verified here (Linux, Electron 45.5.0, virtual display): the 6 unit tests; the security behaviour listed above; offline page; packaging config produces a valid unpacked app with `app-config.json` as a resource.
- **Not verified:** actual Windows and macOS installers (the workflow has never run), installing/opening on either OS, the real KASORA web app's sign-in inside the shell (cookie/Origin behaviour on a real deployed domain), microphone on those systems.
- A single-sign-on or payment page on another domain would be blocked in the window (it opens in the browser instead). None exists today.

## Needs the owner
1. A deployed https address for the web app and API (same site, or cookies configured for cross-site use).
2. **Code signing**: a Windows certificate and an Apple Developer ID plus notarisation. Without them Windows shows "unknown publisher" and macOS blocks the app. Certificates are personal purchases/accounts, so Claude has not touched them.
3. An app icon (`desktop/assets/`, `icon.ico` / `icon.icns` / 1024 px PNG). The default Electron icon is used until then.
4. A decision on automatic updates (needs signing and a place to host releases).

## Not done on purpose
- Staff softphone or calling inside the desktop app: separate work, and real telephony still needs the provider approval steps in `telephony-telnyx.md`.
- Mac App Store / Microsoft Store packaging.
