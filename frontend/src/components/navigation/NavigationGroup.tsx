"use client";

import Link from "next/link";
import { ChevronDown } from "lucide-react";
import { useState } from "react";
import {
  NavigationBadge,
  NavigationItem,
  navLinkClasses,
} from "@/components/navigation/NavigationItem";
import { Tooltip } from "@/components/ui/Tooltip";
import { isRouteActive, type NavBadgeKey, type NavGroup, type NavItem } from "@/lib/constants";
import { cn } from "@/lib/utils";

export type NavBadges = Partial<Record<NavBadgeKey, number>>;

interface NavigationGroupProps {
  group: NavGroup;
  pathname: string;
  collapsed: boolean;
  badges: NavBadges;
  onNavigate?: () => void;
}

/** An item with sub-pages (Communication Center). */
function NavigationParent({
  item,
  pathname,
  collapsed,
  badge,
  onNavigate,
}: {
  item: NavItem;
  pathname: string;
  collapsed: boolean;
  badge: number;
  onNavigate?: () => void;
}) {
  const children = item.children ?? [];
  const childActive = children.some((child) => isRouteActive(pathname, child.href));
  // Open automatically while the user is inside the section; they can still fold it.
  const [userOpen, setUserOpen] = useState<boolean | null>(null);
  const open = userOpen ?? childActive;
  const Icon = item.icon;
  const listId = `nav-sub-${item.id}`;

  // Rail mode has no room for a submenu, so the icon goes to the first sub-page.
  if (collapsed) {
    const first = children[0];
    return (
      <Tooltip content={item.label} side="right">
        <Link
          href={first?.href ?? item.href}
          aria-label={item.label}
          aria-current={childActive ? "page" : undefined}
          onClick={onNavigate}
          className={navLinkClasses(childActive, true)}
        >
          <Icon aria-hidden="true" className="size-[18px] shrink-0" />
          {badge > 0 ? <NavigationBadge count={badge} collapsed /> : null}
        </Link>
      </Tooltip>
    );
  }

  return (
    <div>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={listId}
        onClick={() => setUserOpen(!open)}
        className={cn(navLinkClasses(childActive && !open, false), "w-full gap-2.5")}
      >
        <Icon aria-hidden="true" className="size-[18px] shrink-0" />
        <span className="truncate">{item.label}</span>
        <span className="ml-auto flex items-center gap-1.5">
          {badge > 0 ? <NavigationBadge count={badge} collapsed={false} /> : null}
          <ChevronDown aria-hidden="true" className={cn("size-4 transition-transform", open && "rotate-180")} />
        </span>
      </button>
      {open ? (
        <ul id={listId} className="mt-1 space-y-1">
          {children.map((child) => (
            <li key={child.id}>
              <NavigationItem
                item={child}
                active={isRouteActive(pathname, child.href)}
                collapsed={false}
                nested
                onNavigate={onNavigate}
              />
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

export function NavigationGroup({ group, pathname, collapsed, badges, onNavigate }: NavigationGroupProps) {
  const headingId = `nav-group-${group.id}`;

  return (
    <div role="group" aria-labelledby={headingId}>
      <h2
        id={headingId}
        className={cn(
          "px-3 text-[11px] font-semibold uppercase tracking-wider text-sidebar-muted",
          collapsed ? "sr-only" : "mb-2",
        )}
      >
        {group.label}
      </h2>
      {collapsed ? <div aria-hidden="true" className="mx-auto mb-2 h-px w-6 bg-sidebar-border" /> : null}
      <ul className={cn("space-y-1", collapsed && "flex flex-col items-center")}>
        {group.items.map((item) => {
          const badge = item.badgeKey ? (badges[item.badgeKey] ?? 0) : 0;
          return (
            <li key={item.id} className={cn(!collapsed && "w-full")}>
              {item.children ? (
                <NavigationParent
                  item={item}
                  pathname={pathname}
                  collapsed={collapsed}
                  badge={badge}
                  onNavigate={onNavigate}
                />
              ) : (
                <NavigationItem
                  item={item}
                  active={isRouteActive(pathname, item.href)}
                  collapsed={collapsed}
                  badge={badge}
                  onNavigate={onNavigate}
                />
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
