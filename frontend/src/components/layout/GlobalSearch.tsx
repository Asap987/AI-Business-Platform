"use client";

import { CornerDownLeft, Search } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useId, useMemo, useState } from "react";
import { Modal } from "@/components/ui/Modal";
import { NAV_GROUPS } from "@/lib/constants";
import { cn } from "@/lib/utils";

interface SearchEntry {
  id: string;
  label: string;
  href: string;
  section: string;
}

/** The only data searched today is the app's own pages; see the notice below. */
const ENTRIES: SearchEntry[] = NAV_GROUPS.flatMap((group) =>
  group.items.flatMap((item) => [
    { id: item.id, label: item.label, href: item.children ? item.children[0].href : item.href, section: group.label },
    ...(item.children ?? []).map((child) => ({
      id: child.id,
      label: `${item.label} › ${child.label}`,
      href: child.href,
      section: group.label,
    })),
  ]),
);

function SearchPanel({ onNavigate, autoFocus = false }: { onNavigate?: () => void; autoFocus?: boolean }) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const uid = useId();
  const inputId = `${uid}-search`;
  const noteId = `${uid}-search-note`;

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    return ENTRIES.filter((entry) => entry.label.toLowerCase().includes(q)).slice(0, 8);
  }, [query]);

  // Called after a result is chosen. Links navigate on their own; Enter uses router.push.
  const done = () => {
    setQuery("");
    onNavigate?.();
  };

  return (
    <div className="group relative">
      <form
        role="search"
        onSubmit={(event) => {
          event.preventDefault();
          if (results[0]) {
            router.push(results[0].href);
            done();
          }
        }}
      >
        <label htmlFor={inputId} className="sr-only">
          Search pages
        </label>
        <Search aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" />
        <input
          id={inputId}
          type="search"
          value={query}
          autoFocus={autoFocus}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search pages…"
          autoComplete="off"
          aria-describedby={noteId}
          className="h-10 w-full rounded-lg border border-border-strong bg-surface pl-9 pr-3 text-sm text-ink placeholder:text-muted [&::-webkit-search-cancel-button]:hidden"
        />
      </form>

      {query.trim() ? (
        <div
          className={cn(
            "absolute left-0 right-0 z-50 mt-2 overflow-hidden rounded-xl border border-border bg-surface shadow-pop",
            // Inline on desktop: only open while the box (or a result) has focus.
            "lg:hidden lg:group-focus-within:block",
            autoFocus && "lg:block",
          )}
        >
          {results.length > 0 ? (
            <ul aria-label="Search results" className="p-1.5">
              {results.map((entry) => (
                <li key={entry.id}>
                  <Link
                    href={entry.href}
                    onClick={done}
                    className="flex items-center justify-between gap-3 rounded-lg px-3 py-2 text-sm text-ink hover:bg-surface-muted"
                  >
                    <span className="truncate">{entry.label}</span>
                    <span className="shrink-0 text-xs text-muted">{entry.section}</span>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <p role="status" className="px-4 py-3 text-sm text-muted">
              No pages match &ldquo;{query.trim()}&rdquo;.
            </p>
          )}
          <p className="flex items-center gap-1.5 border-t border-border bg-surface-muted px-4 py-2 text-xs text-muted">
            <CornerDownLeft aria-hidden="true" className="size-3" />
            Press Enter to open the first result.
          </p>
        </div>
      ) : null}

      <p id={noteId} className="sr-only">
        Searches page names only. Searching customers, cases and conversations needs a backend search endpoint that
        doesn&apos;t exist yet.
      </p>
    </div>
  );
}

/**
 * Header search. Placeholder scope: it finds app pages only. Searching
 * customers, cases and conversations is blocked on a backend /search endpoint
 * (documented in the API contract), and the UI says so rather than pretending.
 */
export function GlobalSearch() {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <>
      <div className="hidden w-64 xl:w-80 lg:block">
        <SearchPanel />
      </div>

      <button
        type="button"
        onClick={() => setMobileOpen(true)}
        aria-label="Search pages"
        className="inline-flex size-10 items-center justify-center rounded-lg text-muted hover:bg-surface-muted hover:text-ink lg:hidden"
      >
        <Search aria-hidden="true" className="size-5" />
      </button>

      <Modal
        open={mobileOpen}
        onClose={() => setMobileOpen(false)}
        title="Search"
        description="Search pages only. Customer, case and conversation search isn't available yet."
      >
        {mobileOpen ? <SearchPanel autoFocus onNavigate={() => setMobileOpen(false)} /> : null}
      </Modal>
    </>
  );
}
