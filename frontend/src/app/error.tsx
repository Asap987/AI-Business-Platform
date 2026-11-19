"use client";

import { ErrorMessage } from "@/components/ui/ErrorMessage";

/** Last-resort boundary so an unexpected rendering error never leaves a blank screen. */
export default function GlobalError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <main className="flex min-h-dvh items-center justify-center bg-canvas p-4">
      <ErrorMessage
        error="An unexpected error stopped this page from loading. Your data is safe."
        title="Something went wrong"
        onRetry={reset}
      />
    </main>
  );
}
