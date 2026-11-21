import type { Metadata } from "next";
import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";

export const metadata: Metadata = { title: "Account Settings" };

export default function AccountSettingsPage() {
  return <ModulePlaceholder module="account" />;
}
