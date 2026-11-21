import { Building2, User, UserCog, Users } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { PageHeader } from "@/components/layout/PageHeader";
import { Card } from "@/components/ui/Card";

export const metadata: Metadata = { title: "Settings" };

const SECTIONS = [
  { href: "/settings/profile", title: "My Profile", description: "Your name and contact details.", icon: User },
  { href: "/settings/account", title: "Account Settings", description: "Password and sign-in security.", icon: UserCog },
  { href: "/settings/team", title: "Team", description: "Invite staff, change roles, disable logins.", icon: Users },
  { href: "/settings/business", title: "Business Settings", description: "Business details and preferences.", icon: Building2 },
] as const;

export default function SettingsPage() {
  return (
    <>
      <PageHeader title="Settings" description="Manage your profile, account and business." />
      <ul className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {SECTIONS.map(({ href, title, description, icon: Icon }) => (
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
    </>
  );
}
