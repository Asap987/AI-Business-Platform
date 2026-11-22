import type { Metadata } from "next";
import { PrivacyView } from "@/features/privacy/PrivacyView";

export const metadata: Metadata = { title: "Privacy & AI" };

export default function PrivacyPage() {
  return <PrivacyView />;
}
