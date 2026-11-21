"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";
import { ErrorMessage } from "@/components/ui/ErrorMessage";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { safeNextPath } from "@/lib/utils";
import { useAuth } from "@/providers/AuthProvider";

function FullPageSpinner({ label }: { label: string }) {
  return (
    <div className="flex min-h-dvh items-center justify-center bg-canvas">
      <LoadingSpinner size="lg" label={label} />
    </div>
  );
}

/**
 * Wraps authenticated pages. This is a usability guard, not a security
 * boundary: the backend must enforce access on every request regardless.
 */
export function AuthGuard({ children }: { children: ReactNode }) {
  const { status, error, sessionExpired, signedOut, retrySession } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (status !== "unauthenticated") return;
    const params = new URLSearchParams();
    // After a deliberate sign-out there is nothing to "return to".
    if (!signedOut && pathname && pathname !== "/dashboard") params.set("next", pathname);
    if (sessionExpired) params.set("expired", "1");
    const query = params.toString();
    router.replace(query ? `/login?${query}` : "/login");
  }, [status, sessionExpired, signedOut, pathname, router]);

  if (status === "loading") return <FullPageSpinner label="Checking your session" />;

  if (status === "error" && error) {
    return (
      <div className="flex min-h-dvh items-center justify-center bg-canvas p-4">
        <ErrorMessage error={error} onRetry={retrySession} title="We couldn't check your session" />
      </div>
    );
  }

  if (status !== "authenticated") return <FullPageSpinner label="Redirecting to sign in" />;

  return <>{children}</>;
}

/** Wraps login/register pages: signed-in users are sent on to the app. */
export function GuestGuard({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (status !== "authenticated") return;
    const next = new URLSearchParams(window.location.search).get("next");
    router.replace(safeNextPath(next));
  }, [status, router]);

  if (status === "loading" || status === "authenticated") {
    return <FullPageSpinner label={status === "loading" ? "Checking your session" : "Redirecting"} />;
  }

  // "unauthenticated" and "error" (backend unreachable) both show the form, so
  // the person sees a clear error when they try to sign in.
  return <>{children}</>;
}
