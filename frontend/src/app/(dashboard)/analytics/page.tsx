import type { Metadata } from "next";
import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";

export const metadata: Metadata = { title: "Analytics & Reports" };

export default function AnalyticsPage() {
  return <ModulePlaceholder module="analytics" />;
}
