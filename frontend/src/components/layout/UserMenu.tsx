"use client";

import { Building2, ChevronDown, LogOut, User, UserCog } from "lucide-react";
import { Avatar } from "@/components/ui/Avatar";
import { Dropdown } from "@/components/ui/Dropdown";
import { useAuth } from "@/providers/AuthProvider";

export function UserMenu() {
  const { user, logout } = useAuth();
  const name = user?.full_name ?? "Account";
  const role = user?.role.name ?? "";

  return (
    <Dropdown
      label="Account menu"
      header={
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-ink">{name}</p>
          {user?.email ? <p className="truncate text-xs text-muted">{user.email}</p> : null}
        </div>
      }
      items={[
        { id: "profile", label: "My Profile", href: "/settings/profile", icon: <User aria-hidden="true" className="size-4 text-muted" /> },
        { id: "account", label: "Account Settings", href: "/settings/account", icon: <UserCog aria-hidden="true" className="size-4 text-muted" /> },
        { id: "business", label: "Business Settings", href: "/settings/business", icon: <Building2 aria-hidden="true" className="size-4 text-muted" /> },
        {
          id: "signout",
          label: "Sign Out",
          icon: <LogOut aria-hidden="true" className="size-4" />,
          tone: "danger",
          separatorBefore: true,
          // The route guard redirects to /login once the session is cleared.
          onSelect: () => {
            void logout();
          },
        },
      ]}
      renderTrigger={(props) => (
        <button
          type="button"
          {...props}
          aria-label={`Account menu for ${name}${role ? `, ${role}` : ""}`}
          className="flex items-center gap-2.5 rounded-lg py-1 pl-1 pr-2 hover:bg-surface-muted"
        >
          <Avatar name={name} />
          <span className="hidden min-w-0 text-left md:block">
            <span className="block max-w-36 truncate text-sm font-medium leading-tight text-ink">{name}</span>
            <span className="block max-w-36 truncate text-xs leading-tight text-muted">{role}</span>
          </span>
          <ChevronDown aria-hidden="true" className="hidden size-4 text-muted md:block" />
        </button>
      )}
    />
  );
}
