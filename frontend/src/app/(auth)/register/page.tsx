import type { Metadata } from "next";
import { RegisterForm } from "@/features/auth/RegisterForm";

export const metadata: Metadata = { title: "Register your business" };

export default function RegisterPage() {
  return <RegisterForm />;
}
