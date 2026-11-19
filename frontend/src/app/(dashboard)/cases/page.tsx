import type { Metadata } from "next";
import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";

export const metadata: Metadata = { title: "Cases & Escalations" };

export default function CasesPage() {
  return <ModulePlaceholder module="cases" />;
}
