import type { Metadata } from "next";
import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";

export const metadata: Metadata = { title: "Workflows" };

export default function WorkflowsPage() {
  return <ModulePlaceholder module="workflows" />;
}
