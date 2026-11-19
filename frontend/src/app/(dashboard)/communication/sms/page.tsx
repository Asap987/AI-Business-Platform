import type { Metadata } from "next";
import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";

export const metadata: Metadata = { title: "SMS Inbox" };

export default function SmsPage() {
  return <ModulePlaceholder module="sms" />;
}
