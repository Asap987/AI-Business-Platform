import type { Metadata } from "next";
import { CaseDetailView } from "@/features/cases/CaseDetailView";

export const metadata: Metadata = { title: "Case" };

export default function CaseDetailPage() {
  return <CaseDetailView />;
}
