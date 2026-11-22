import type { Metadata } from "next";
import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";

export const metadata: Metadata = { title: "Conversations" };

export default function ConversationsPage() {
  return <ModulePlaceholder module="conversations" />;
}
