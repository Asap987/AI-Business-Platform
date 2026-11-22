import type { Metadata } from "next";
import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";

export const metadata: Metadata = { title: "Help & Support" };

export default function HelpPage() {
  return <ModulePlaceholder module="help" />;
}
