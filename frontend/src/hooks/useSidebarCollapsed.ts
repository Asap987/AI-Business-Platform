"use client";

import { useCallback, useSyncExternalStore } from "react";

const STORAGE_KEY = "cc.sidebar";
const CHANGE_EVENT = "cc:sidebar-change";
const DESKTOP_QUERY = "(min-width: 1024px)";

type SidebarPreference = "collapsed" | "expanded";

function readStored(): SidebarPreference | null {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    return value === "collapsed" || value === "expanded" ? value : null;
  } catch {
    // Storage can be blocked (private mode, strict settings); fall back to defaults.
    return null;
  }
}

function getSnapshot(): SidebarPreference {
  // Until the user chooses, tablets start as a compact rail and desktops expanded.
  return readStored() ?? (window.matchMedia(DESKTOP_QUERY).matches ? "expanded" : "collapsed");
}

function getServerSnapshot(): SidebarPreference {
  return "expanded";
}

function subscribe(onChange: () => void): () => void {
  const media = window.matchMedia(DESKTOP_QUERY);
  window.addEventListener("storage", onChange);
  window.addEventListener(CHANGE_EVENT, onChange);
  media.addEventListener("change", onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(CHANGE_EVENT, onChange);
    media.removeEventListener("change", onChange);
  };
}

/**
 * Whether the desktop sidebar is folded to an icon rail. The choice is a UI
 * preference only (no business data), so localStorage is appropriate here.
 */
export function useSidebarCollapsed(): { collapsed: boolean; toggle: () => void } {
  const preference = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  const toggle = useCallback(() => {
    const next: SidebarPreference = getSnapshot() === "collapsed" ? "expanded" : "collapsed";
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Ignore: the toggle still works for this page view via the event below.
    }
    window.dispatchEvent(new Event(CHANGE_EVENT));
  }, []);

  return { collapsed: preference === "collapsed", toggle };
}
