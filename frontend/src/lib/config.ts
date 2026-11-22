/**
 * Central API configuration. Every backend URL in the app is built from these
 * values; components must never hardcode a host or path prefix.
 */

const rawBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const rawPrefix = process.env.NEXT_PUBLIC_API_PREFIX ?? "/api/v1";
const rawTimeout = Number(process.env.NEXT_PUBLIC_API_TIMEOUT_MS ?? 15000);

export const API_BASE_URL = rawBaseUrl.replace(/\/+$/, "");

export const API_PREFIX = rawPrefix === "" ? "" : `/${rawPrefix.replace(/^\/+|\/+$/g, "")}`;

export const API_TIMEOUT_MS =
  Number.isFinite(rawTimeout) && rawTimeout > 0 ? rawTimeout : 15000;

export const APP_NAME = "KASORA AI";
