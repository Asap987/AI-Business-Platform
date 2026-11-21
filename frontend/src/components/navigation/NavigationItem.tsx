import Link from "next/link";
import { Tooltip } from "@/components/ui/Tooltip";
import type { NavChild, NavItem } from "@/lib/constants";
import { cn } from "@/lib/utils";

interface NavigationItemProps {
  item: NavItem | NavChild;
  active: boolean;
  collapsed: boolean;
  /** Unread/attention counter shown as a badge. */
  badge?: number;
  /** Indented sub-item inside an expanded parent. */
  nested?: boolean;
  onNavigate?: () => void;
}

export function NavigationBadge({ count, collapsed }: { count: number; collapsed: boolean }) {
  const text = count > 99 ? "99+" : String(count);
  return (
    <span
      className={cn(
        "flex min-w-5 items-center justify-center rounded-full bg-accent px-1.5 text-[11px] font-semibold leading-5 text-on-primary",
        collapsed && "absolute right-1 top-1 min-w-4 px-1 text-[10px] leading-4",
      )}
    >
      {text}
      <span className="sr-only"> unread</span>
    </span>
  );
}

export function navLinkClasses(active: boolean, collapsed: boolean, nested = false): string {
  return cn(
    "relative flex items-center gap-3 rounded-lg text-sm font-medium transition-colors",
    collapsed ? "size-10 justify-center" : nested ? "h-9 px-3 pl-10" : "h-10 px-3",
    active
      ? "bg-sidebar-active text-sidebar-text-strong"
      : "text-sidebar-text hover:bg-sidebar-hover hover:text-sidebar-text-strong",
  );
}

export function NavigationItem({ item, active, collapsed, badge = 0, nested = false, onNavigate }: NavigationItemProps) {
  const Icon = item.icon;

  return (
    <Tooltip content={item.label} side="right" disabled={!collapsed}>
      <Link
        href={item.href}
        aria-current={active ? "page" : undefined}
        aria-label={collapsed ? item.label : undefined}
        onClick={onNavigate}
        className={navLinkClasses(active, collapsed, nested)}
      >
        {active && !nested ? (
          <span aria-hidden="true" className="absolute inset-y-2 left-0 w-0.5 rounded-full bg-accent" />
        ) : null}
        {nested && !collapsed ? null : <Icon aria-hidden="true" className="size-[18px] shrink-0" />}
        {collapsed ? null : <span className="truncate">{item.label}</span>}
        {badge > 0 ? (
          <span className={cn(!collapsed && "ml-auto")}>
            <NavigationBadge count={badge} collapsed={collapsed} />
          </span>
        ) : null}
      </Link>
    </Tooltip>
  );
}
