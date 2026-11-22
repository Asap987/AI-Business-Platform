"use client";

import { BusinessSwitcher } from "@/components/layout/BusinessSwitcher";
import type { NavBadges } from "@/components/navigation/NavigationGroup";
import { SidebarNav } from "@/components/navigation/SidebarNav";
import { cn } from "@/lib/utils";

interface SidebarProps {
  collapsed: boolean;
  badges: NavBadges;
}

/** Persistent desktop/tablet sidebar. Below md the MobileNavigation drawer is used instead. */
export function Sidebar({ collapsed, badges }: SidebarProps) {
  return (
    <aside
      id="app-sidebar"
      className={cn(
        "sticky top-0 hidden h-dvh shrink-0 flex-col border-r border-sidebar-border bg-sidebar transition-[width] duration-200 md:flex",
        // Wide enough for "Communication Center" plus its unread badge and chevron.
        collapsed ? "w-[4.5rem]" : "w-[18.5rem]",
      )}
    >
      <div className={cn("border-b border-sidebar-border py-4", collapsed ? "px-3" : "px-4")}>
        <BusinessSwitcher collapsed={collapsed} />
      </div>
      {/* Tooltips in rail mode sit outside the rail, so it must not clip them. */}
      <div className={cn("flex-1 px-3 py-5", collapsed ? "overflow-visible" : "overflow-y-auto")}>
        <SidebarNav collapsed={collapsed} badges={badges} />
      </div>
    </aside>
  );
}
