import type { Metadata } from "next";
import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";

export const metadata: Metadata = { title: "Departments" };

export default function DepartmentsPage() {
  return <ModulePlaceholder module="departments" />;
}
