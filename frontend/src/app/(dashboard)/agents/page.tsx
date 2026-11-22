import type { Metadata } from "next";
import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";

export const metadata: Metadata = { title: "AI Agents" };

export default function AgentsPage() {
  return <ModulePlaceholder module="agents" />;
}
