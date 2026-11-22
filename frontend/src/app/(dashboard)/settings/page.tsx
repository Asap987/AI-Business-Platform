import type { Metadata } from "next";
import { PageHeader } from "@/components/layout/PageHeader";
import { SettingsLinks } from "@/features/settings/SettingsLinks";

export const metadata: Metadata = { title: "Settings" };

export default function SettingsPage() {
  return (
    <>
      <PageHeader title="Settings" description="Manage your profile, account and business." />
      <SettingsLinks />
    </>
  );
}
