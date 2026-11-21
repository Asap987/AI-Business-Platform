import type { Metadata } from "next";
import { DepartmentsView } from "@/features/departments/DepartmentsView";

export const metadata: Metadata = { title: "Departments" };

export default function DepartmentsPage() {
  return <DepartmentsView />;
}
