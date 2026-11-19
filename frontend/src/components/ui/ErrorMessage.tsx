import { CircleAlert, Lock, WifiOff } from "lucide-react";
import { Button, ButtonLink } from "@/components/ui/Button";
import type { ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

interface ErrorMessageProps {
  /** An ApiError gets tailored copy; a plain string is shown as-is. */
  error: ApiError | string;
  title?: string;
  onRetry?: () => void;
  /** Smaller padding for use inside cards. */
  compact?: boolean;
  className?: string;
}

function describe(error: ApiError | string): {
  title: string;
  message: string;
  Icon: typeof CircleAlert;
  retryable: boolean;
  signIn: boolean;
} {
  if (typeof error === "string") {
    return { title: "Something went wrong", message: error, Icon: CircleAlert, retryable: true, signIn: false };
  }
  switch (error.kind) {
    case "forbidden":
      return {
        title: "Permission denied",
        message: "Your role doesn't include access to this. Ask an administrator if you think that's a mistake.",
        Icon: Lock,
        retryable: false,
        signIn: false,
      };
    case "unauthorized":
      return {
        title: "Session expired",
        message: "Please sign in again to continue.",
        Icon: Lock,
        retryable: false,
        signIn: true,
      };
    case "network":
    case "timeout":
      return { title: "Can't reach the server", message: error.message, Icon: WifiOff, retryable: true, signIn: false };
    case "not_found":
      return {
        title: "Not available yet",
        message: "The backend doesn't provide this data yet. It will appear here once it does.",
        Icon: CircleAlert,
        retryable: true,
        signIn: false,
      };
    default:
      return { title: "Something went wrong", message: error.message, Icon: CircleAlert, retryable: true, signIn: false };
  }
}

export function ErrorMessage({ error, title, onRetry, compact = false, className }: ErrorMessageProps) {
  const info = describe(error);
  return (
    <div
      role="alert"
      className={cn("flex flex-col items-center justify-center text-center", compact ? "px-4 py-8" : "px-6 py-14", className)}
    >
      <span className="mb-3 flex size-11 items-center justify-center rounded-full bg-danger-soft text-danger">
        <info.Icon aria-hidden="true" className="size-5" />
      </span>
      <p className="text-sm font-semibold text-ink">{title ?? info.title}</p>
      <p className="mt-1 max-w-sm text-sm text-muted">{info.message}</p>
      <div className="mt-4 flex gap-2">
        {info.signIn ? (
          <ButtonLink href="/login" variant="primary" size="sm">
            Sign in
          </ButtonLink>
        ) : null}
        {info.retryable && onRetry ? (
          <Button variant="secondary" size="sm" onClick={onRetry}>
            Try again
          </Button>
        ) : null}
      </div>
    </div>
  );
}

/** Inline form-level error banner (login failures and similar). */
export function FormError({ message }: { message: string }) {
  return (
    <div role="alert" className="flex gap-2.5 rounded-lg border border-danger/30 bg-danger-soft px-3.5 py-3 text-sm text-danger">
      <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
      <p>{message}</p>
    </div>
  );
}
