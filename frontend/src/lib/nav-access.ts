import type { NavGroup } from "@/lib/constants";

/**
 * Removes the navigation entries the signed-in role may not use, and any group or parent left empty.
 * This only tidies the menu: pages still check for themselves and the backend enforces every endpoint.
 */
export function filterNavGroups(groups: readonly NavGroup[], mayUse: (permission: string) => boolean): NavGroup[] {
  const allowed = (needed?: string) => !needed || mayUse(needed);
  return groups
    .map((group) => ({
      ...group,
      items: group.items
        .filter((item) => allowed(item.permission))
        .map((item) => (item.children ? { ...item, children: item.children.filter((c) => allowed(c.permission)) } : item))
        .filter((item) => !item.children || item.children.length > 0),
    }))
    .filter((group) => group.items.length > 0);
}
