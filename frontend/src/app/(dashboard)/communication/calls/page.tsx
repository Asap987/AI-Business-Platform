import type { Metadata } from "next";
import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";

export const metadata: Metadata = { title: "Calls" };

export default function CallsPage() {
  return <ModulePlaceholder module="calls" />;
}
