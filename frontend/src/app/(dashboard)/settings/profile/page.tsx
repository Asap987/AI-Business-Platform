import type { Metadata } from "next";
import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";

export const metadata: Metadata = { title: "My Profile" };

export default function ProfilePage() {
  return <ModulePlaceholder module="profile" />;
}
