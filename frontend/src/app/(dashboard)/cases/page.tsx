import type { Metadata } from "next";
import { CasesView } from "@/features/cases/CasesView";

export const metadata: Metadata = { title: "Cases & Escalations" };

export default function CasesPage() {
  return <CasesView />;
}
