import type { Metadata } from "next";
import { EmployeesView } from "@/features/employees/EmployeesView";

export const metadata: Metadata = { title: "Employees" };

export default function EmployeesPage() {
  return <EmployeesView />;
}
