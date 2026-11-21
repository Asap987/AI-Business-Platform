import type { Metadata } from "next";
import { CustomerDetailView } from "@/features/customers/CustomerDetailView";

export const metadata: Metadata = { title: "Customer" };

export default function CustomerDetailPage() {
  return <CustomerDetailView />;
}
