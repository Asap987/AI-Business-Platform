"use client";

import { Bell, BellOff } from "lucide-react";
import Link from "next/link";
import { EmptyState } from "@/components/ui/EmptyState";
import { Popover } from "@/components/ui/Popover";
import { ResourceView } from "@/components/ui/ResourceView";
import { Skeleton } from "@/components/ui/LoadingSpinner";
import { Tooltip } from "@/components/ui/Tooltip";
import type { ApiResource } from "@/hooks/useApiResource";
import { cn, formatRelativeTime } from "@/lib/utils";
import type { NotificationSummary } from "@/types/api";

export function NotificationsMenu({ resource }: { resource: ApiResource<NotificationSummary> }) {
  const unread = resource.status === "success" ? (resource.data?.unread_total ?? 0) : 0;
  const label = unread > 0 ? `Notifications, ${unread} unread` : "Notifications";

  return (
    <Popover
      label="Notifications"
      panelClassName="w-[min(22rem,calc(100vw-2rem))]"
      renderTrigger={(props) => (
        <Tooltip content="Notifications">
          <button
            type="button"
            {...props}
            aria-label={label}
            className="relative inline-flex size-10 items-center justify-center rounded-lg text-muted hover:bg-surface-muted hover:text-ink"
          >
            <Bell aria-hidden="true" className="size-5" />
            {unread > 0 ? (
              <span
                aria-hidden="true"
                className="absolute right-1 top-1 flex min-w-4 items-center justify-center rounded-full bg-accent-strong px-1 text-[10px] font-semibold leading-4 text-on-primary"
              >
                {unread > 99 ? "99+" : unread}
              </span>
            ) : null}
          </button>
        </Tooltip>
      )}
    >
      {(close) => (
        <div>
          <div className="border-b border-border px-4 py-3">
            <h2 className="text-sm font-semibold text-ink">Notifications</h2>
          </div>
          <div className="max-h-96 overflow-y-auto">
            <ResourceView
              resource={resource}
              isEmpty={(data) => data.items.length === 0}
              skeleton={
                <div className="space-y-3 p-4">
                  <Skeleton className="h-10" />
                  <Skeleton className="h-10" />
                  <Skeleton className="h-10" />
                </div>
              }
              empty={<EmptyState compact icon={BellOff} title="You're all caught up" description="New notifications will show up here." />}
            >
              {(data) => (
                <ul className="divide-y divide-border">
                  {data.items.map((item) => {
                    const body = (
                      <>
                        <span className="flex items-start gap-2">
                          {!item.read ? (
                            <span aria-hidden="true" className="mt-1.5 size-2 shrink-0 rounded-full bg-accent" />
                          ) : null}
                          <span className={cn("min-w-0", item.read && "pl-4")}>
                            <span className="block text-sm font-medium text-ink">
                              {!item.read ? <span className="sr-only">Unread: </span> : null}
                              {item.title}
                            </span>
                            {item.body ? <span className="mt-0.5 block text-sm text-muted">{item.body}</span> : null}
                            <span className="mt-1 block text-xs text-muted">{formatRelativeTime(item.created_at)}</span>
                          </span>
                        </span>
                      </>
                    );
                    return (
                      <li key={item.id}>
                        {item.href ? (
                          <Link href={item.href} onClick={close} className="block px-4 py-3 hover:bg-surface-muted">
                            {body}
                          </Link>
                        ) : (
                          <div className="px-4 py-3">{body}</div>
                        )}
                      </li>
                    );
                  })}
                </ul>
              )}
            </ResourceView>
          </div>
        </div>
      )}
    </Popover>
  );
}
