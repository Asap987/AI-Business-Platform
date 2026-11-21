"use client";

import { usePathname } from "next/navigation";
import { NavigationGroup, type NavBadges } from "@/components/navigation/NavigationGroup";
import { NAV_GROUPS } from "@/lib/constants";

interface SidebarNavProps {
  collapsed: boolean;
  badges: NavBadges;
  onNavigate?: () => void;
}

/** The navigation list shared by the desktop sidebar and the mobile drawer. */
export function SidebarNav({ collapsed, badges, onNavigate }: SidebarNavProps) {
  const pathname = usePathname();

  return (
    <nav aria-label="Main navigation" className="space-y-6">
      {NAV_GROUPS.map((group) => (
        <NavigationGroup
          key={group.id}
          group={group}
          pathname={pathname}
          collapsed={collapsed}
          badges={badges}
          onNavigate={onNavigate}
        />
      ))}
    </nav>
  );
}
