"use client";

import { CircleCheck } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { AuthFormLayout } from "@/features/auth/AuthFormLayout";
import { ApiError } from "@/lib/api";
import { verifyEmailRequest } from "@/lib/auth";

type State = "working" | "done" | "invalid" | "error";

/** The token arrives in the URL fragment, is used once and removed from the address bar. */
export function VerifyEmailPanel() {
  const [state, setState] = useState<State>("working");

  useEffect(() => {
    const token = new URLSearchParams(window.location.hash.replace(/^#/, "")).get("token");
    if (token) window.history.replaceState(null, "", window.location.pathname);
    const run = token ? verifyEmailRequest(token) : Promise.reject(new ApiError({ status: 404, kind: "not_found", message: "No token" }));
    run
      .then(() => setState("done"))
      .catch((error: unknown) => setState(error instanceof ApiError && error.status === 404 ? "invalid" : "error"));
  }, []);

  const back = (
    <Link href="/dashboard" className="font-medium text-accent-strong hover:underline">
      Go to your dashboard
    </Link>
  );

  if (state === "working") return <AuthFormLayout title="Confirming your email" description="One moment…" footer={back}>{null}</AuthFormLayout>;
  if (state === "done") {
    return (
      <AuthFormLayout title="Email confirmed" description="Thank you. Your address is confirmed." footer={back}>
        <div role="status" className="flex items-start gap-3 rounded-lg border border-success/30 bg-success-soft px-4 py-3.5 text-sm text-success">
          <CircleCheck aria-hidden="true" className="mt-0.5 size-5 shrink-0" />
          <p>You can close this tab or continue.</p>
        </div>
      </AuthFormLayout>
    );
  }
  return (
    <AuthFormLayout
      title={state === "invalid" ? "This link can't be used" : "Something went wrong"}
      description={state === "invalid" ? "It may have expired or already been used. Sign in and ask for a new confirmation email." : "Please try the link again in a moment."}
      footer={<Link href="/login" className="font-medium text-accent-strong hover:underline">Sign in</Link>}
    >
      {null}
    </AuthFormLayout>
  );
}
