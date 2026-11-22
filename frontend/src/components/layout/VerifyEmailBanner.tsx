"use client";

import { MailWarning } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { ApiError } from "@/lib/api";
import { resendVerificationRequest } from "@/lib/auth";
import { useAuth } from "@/providers/AuthProvider";

type State = { kind: "idle" } | { kind: "sending" } | { kind: "sent" } | { kind: "error"; message: string };

/** Shown only when the server says email is on and this address is not confirmed yet. */
export function VerifyEmailBanner() {
  const { user, retrySession } = useAuth();
  const [state, setState] = useState<State>({ kind: "idle" });
  if (!user?.email_verification_required) return null;

  async function send() {
    setState({ kind: "sending" });
    try {
      await resendVerificationRequest();
      setState({ kind: "sent" });
    } catch (error) {
      setState({ kind: "error", message: error instanceof ApiError ? error.message : "Could not send the email. Please try again." });
    }
  }

  return (
    <div role="status" className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-warning/30 bg-warning-soft px-4 py-2.5 text-sm text-ink md:px-8">
      <MailWarning aria-hidden="true" className="size-4 shrink-0 text-warning" />
      <p className="min-w-0 flex-1">
        {state.kind === "sent"
          ? `We sent a confirmation link to ${user.email}. Open it, then come back and refresh.`
          : state.kind === "error"
            ? state.message
            : `Please confirm ${user.email}. You can't invite people until you do.`}
      </p>
      {state.kind === "sent" ? (
        <Button size="sm" variant="secondary" onClick={retrySession}>
          I&apos;ve confirmed it
        </Button>
      ) : (
        <Button size="sm" variant="secondary" loading={state.kind === "sending"} loadingLabel="Sending" onClick={() => void send()}>
          Send confirmation email
        </Button>
      )}
    </div>
  );
}
