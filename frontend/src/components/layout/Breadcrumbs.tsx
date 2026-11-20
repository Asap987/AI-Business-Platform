"use client";

import { ChevronRight } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ROUTE_LABELS } from "@/lib/constants";
import { humanize } from "@/lib/utils";

interface Crumb {
  href: string;
  label: string;
}

const UUID_SEGMENT = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function buildCrumbs(pathname: string): Crumb[] {
  const segments = pathname.split("/").filter(Boolean);
  // Every page lives under the Overview root, which is also the dashboard itself.
  const crumbs: Crumb[] = [{ href: "/dashboard", label: ROUTE_LABELS.dashboard }];

  segments.forEach((segment, index) => {
    if (index === 0 && segment === "dashboard") return;
    crumbs.push({
      href: `/${segments.slice(0, index + 1).join("/")}`,
      // A record id in the URL is not a readable label.
      label: UUID_SEGMENT.test(segment) ? "Details" : (ROUTE_LABELS[segment] ?? humanize(decodeURIComponent(segment))),
    });
  });

  return crumbs;
}

/** Breadcrumb trail derived from the URL, so new routes need no extra wiring. */
export function Breadcrumbs() {
  const pathname = usePathname();
  const crumbs = buildCrumbs(pathname);
  const current = crumbs[crumbs.length - 1];

  return (
    <>
      <nav aria-label="Breadcrumb" className="hidden min-w-0 md:block">
        <ol className="flex items-center gap-1.5 text-sm">
          {crumbs.map((crumb, index) => {
            const last = index === crumbs.length - 1;
            return (
              <li key={crumb.href} className="flex min-w-0 items-center gap-1.5">
                {index > 0 ? <ChevronRight aria-hidden="true" className="size-3.5 shrink-0 text-muted" /> : null}
                {last ? (
                  <span aria-current="page" className="truncate font-medium text-ink">
                    {crumb.label}
                  </span>
                ) : (
                  <Link href={crumb.href} className="truncate text-muted hover:text-ink">
                    {crumb.label}
                  </Link>
                )}
              </li>
            );
          })}
        </ol>
      </nav>
      {/* On phones there's no room for the trail; show just where you are. */}
      <p className="truncate text-sm font-semibold text-ink md:hidden">{current.label}</p>
    </>
  );
}
