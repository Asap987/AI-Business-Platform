import type { Metadata } from "next";
import { VerifyEmailPanel } from "@/features/auth/VerifyEmailPanel";

export const metadata: Metadata = { title: "Confirm your email" };

export default function VerifyEmailPage() {
  return <VerifyEmailPanel />;
}
