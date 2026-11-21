"use client";

import type { ReactNode } from "react";
import { AuthProvider } from "@/providers/AuthProvider";

/** Single place to add future app-wide providers (theme, toasts, ...). */
export function Providers({ children }: { children: ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>;
}
