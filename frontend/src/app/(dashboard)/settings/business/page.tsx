import type { Metadata } from "next";
import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";

export const metadata: Metadata = { title: "Business Settings" };

export default function BusinessSettingsPage() {
  return <ModulePlaceholder module="business" />;
}
