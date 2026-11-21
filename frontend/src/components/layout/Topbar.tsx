"use client";

import { CircleHelp, Menu, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { GlobalSearch } from "@/components/layout/GlobalSearch";
import { NotificationsMenu } from "@/components/layout/NotificationsMenu";
import { UserMenu } from "@/components/layout/UserMenu";
import { Tooltip } from "@/components/ui/Tooltip";
import type { ApiResource } from "@/hooks/useApiResource";
import type { NotificationSummary } from "@/types/api";

interface TopbarProps {
  sidebarCollapsed: boolean;
  onToggleSidebar: () => void;
  onOpenMobileNav: () => void;
  notifications: ApiResource<NotificationSummary>;
}

const ICON_BUTTON =
  "inline-flex size-10 items-center justify-center rounded-lg text-muted hover:bg-surface-muted hover:text-ink";

export function Topbar({ sidebarCollapsed, onToggleSidebar, onOpenMobileNav, notifications }: TopbarProps) {
  const ToggleIcon = sidebarCollapsed ? PanelLeftOpen : PanelLeftClose;

  return (
    <header className="sticky top-0 z-30 flex h-16 shrink-0 items-center gap-3 border-b border-border bg-surface px-4 md:px-6">
      {/* Phones open the drawer; larger screens fold the sidebar to an icon rail. */}
      <button
        type="button"
        onClick={onOpenMobileNav}
        aria-label="Open navigation menu"
        className={`${ICON_BUTTON} md:hidden`}
      >
        <Menu aria-hidden="true" className="size-5" />
      </button>
      <div className="hidden md:block">
        <Tooltip content={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}>
          <button
            type="button"
            onClick={onToggleSidebar}
            aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
            aria-controls="app-sidebar"
            aria-expanded={!sidebarCollapsed}
            className={ICON_BUTTON}
          >
            <ToggleIcon aria-hidden="true" className="size-5" />
          </button>
        </Tooltip>
      </div>

      <div className="min-w-0 flex-1">
        <Breadcrumbs />
      </div>

      <div className="flex items-center gap-1 sm:gap-2">
        <GlobalSearch />
        <NotificationsMenu resource={notifications} />
        <Tooltip content="Help & support">
          <Link href="/help" aria-label="Help and support" className={ICON_BUTTON}>
            <CircleHelp aria-hidden="true" className="size-5" />
          </Link>
        </Tooltip>
        <div className="ml-1 border-l border-border pl-2 sm:ml-2 sm:pl-3">
          <UserMenu />
        </div>
      </div>
    </header>
  );
}
