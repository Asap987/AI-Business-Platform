"use client";

import { Building2, ChartColumn, ShieldCheck, User, UserCog, Users, type LucideIcon } from "lucide-react";
import Link from "next/link";
import { Card } from "@/components/ui/Card";
import { can } from "@/lib/utils";
import { useAuth } from "@/providers/AuthProvider";

interface SettingsLink {
  href: string;
  title: string;
  description: string;
  icon: LucideIcon;
  /** Permission needed to see the card (UX only: the pages and the backend check for themselves). */
  permission?: string;
}

const SECTIONS: SettingsLink[] = [
  { href: "/settings/profile", title: "My Profile", description: "Your name and contact details.", icon: User },
  { href: "/settings/account", title: "Account Settings", description: "Password and sign-in security.", icon: UserCog },
  { href: "/settings/team", title: "Team", description: "Invite staff, change roles, disable logins.", icon: Users, permission: "users:read" },
  { href: "/settings/privacy", title: "Privacy & AI", description: "Control AI providers, masking and the activity log.", icon: ShieldCheck, permission: "privacy:read" },
  { href: "/settings/usage", title: "Usage & costs", description: "Calls, AI usage and estimated cost.", icon: ChartColumn, permission: "usage:read" },
  { href: "/settings/business", title: "Business Settings", description: "Business details and preferences.", icon: Building2 },
];

export function SettingsLinks() {
  const { user } = useAuth();
  const permissions = user?.role.permissions;
  return (
    <ul className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      {SECTIONS.filter((s) => !s.permission || can(permissions, s.permission)).map(({ href, title, description, icon: Icon }) => (
        <li key={href}>
          <Link href={href} className="block h-full rounded-xl">
            <Card className="h-full p-5 transition-colors hover:border-border-strong hover:bg-surface-muted/40">
              <span aria-hidden="true" className="flex size-10 items-center justify-center rounded-lg bg-accent-soft text-accent-strong">
                <Icon className="size-5" />
              </span>
              <h2 className="mt-4 text-base font-semibold text-ink">{title}</h2>
              <p className="mt-1 text-sm text-muted">{description}</p>
            </Card>
          </Link>
        </li>
      ))}
    </ul>
  );
}
