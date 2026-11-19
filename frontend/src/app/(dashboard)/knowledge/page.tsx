import type { Metadata } from "next";
import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";

export const metadata: Metadata = { title: "Knowledge Base" };

export default function KnowledgePage() {
  return <ModulePlaceholder module="knowledge" />;
}
