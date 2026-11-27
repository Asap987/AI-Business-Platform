"use strict";
/**
 * Pure rules for what the desktop window may load and do. No Electron imports, so they are unit-tested with plain Node.
 * The shell is only a window around the web app: the web app and backend enforce accounts, permissions and tenant isolation.
 */

const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1", "[::1]"]);

/** Returns the origin to trust, or throws. Packaged builds accept https only; development also accepts http on localhost. */
function resolveAppOrigin(rawUrl, { packaged }) {
  let u;
  try {
    u = new URL(String(rawUrl || "").trim());
  } catch {
    throw new Error("The KASORA AI address is missing or is not a valid web address.");
  }
  if (u.username || u.password) throw new Error("The KASORA AI address must not contain a user name or password.");
  const local = LOCAL_HOSTS.has(u.hostname);
  if (u.protocol === "https:") return u.origin;
  if (u.protocol === "http:" && local && !packaged) return u.origin;
  throw new Error(packaged ? "The KASORA AI address must start with https://." : "Use https://, or http:// only for localhost.");
}

function isSameOrigin(url, origin) {
  try {
    return new URL(url).origin === origin;
  } catch {
    return false;
  }
}

/** Pages of the app itself may be shown in the window; everything else is refused. */
function allowNavigation(url, origin) {
  return isSameOrigin(url, origin);
}

/** Links to other sites open in the person's normal browser, and only if they are plain web links. */
function allowExternalOpen(url) {
  try {
    const u = new URL(url);
    return u.protocol === "https:" && !u.username && !u.password;
  } catch {
    return false;
  }
}

/** Only the microphone, and only for the app's own pages (used by test calls). Camera, location, notifications etc. are refused. */
function allowPermission(permission, requestingUrl, origin, details = {}) {
  if (!isSameOrigin(requestingUrl, origin)) return false;
  if (permission !== "media") return false;
  const types = details.mediaTypes;
  return Array.isArray(types) ? types.length > 0 && types.every((t) => t === "audio") : false;
}

module.exports = { resolveAppOrigin, isSameOrigin, allowNavigation, allowExternalOpen, allowPermission };
