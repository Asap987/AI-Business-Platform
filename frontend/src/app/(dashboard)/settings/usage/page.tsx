import type { Metadata } from "next";
import { UsageView } from "@/features/usage/UsageView";

export const metadata: Metadata = { title: "Usage & costs" };

export default function UsagePage() {
  return <UsageView />;
}
