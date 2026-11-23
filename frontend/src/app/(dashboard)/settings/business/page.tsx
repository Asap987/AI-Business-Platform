import type { Metadata } from "next";
import { BusinessProfileView } from "@/features/business/BusinessProfileView";

export const metadata: Metadata = { title: "Business Details" };

export default function BusinessSettingsPage() {
  return <BusinessProfileView />;
}
