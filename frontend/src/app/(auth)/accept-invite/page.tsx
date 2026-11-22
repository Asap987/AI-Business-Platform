import type { Metadata } from "next";
import { AcceptInviteForm } from "@/features/auth/AcceptInviteForm";

export const metadata: Metadata = { title: "Accept invitation" };

export default function AcceptInvitePage() {
  return <AcceptInviteForm />;
}
