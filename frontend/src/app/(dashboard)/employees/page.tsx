import type { Metadata } from "next";
import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";

export const metadata: Metadata = { title: "Employees" };

export default function EmployeesPage() {
  return <ModulePlaceholder module="employees" />;
}
