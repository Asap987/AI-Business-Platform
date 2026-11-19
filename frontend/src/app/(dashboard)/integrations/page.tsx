import type { Metadata } from "next";
import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";

export const metadata: Metadata = { title: "Integrations" };

export default function IntegrationsPage() {
  return <ModulePlaceholder module="integrations" />;
}
