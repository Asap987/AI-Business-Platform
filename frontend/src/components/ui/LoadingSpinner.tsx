import { LoaderCircle } from "lucide-react";
import { cn } from "@/lib/utils";

interface LoadingSpinnerProps {
  size?: "sm" | "md" | "lg";
  /** Screen-reader text. Defaults to "Loading". */
  label?: string;
  className?: string;
}

const SIZES = { sm: "size-4", md: "size-6", lg: "size-8" } as const;

export function LoadingSpinner({ size = "md", label = "Loading", className }: LoadingSpinnerProps) {
  return (
    <span role="status" className={cn("inline-flex items-center", className)}>
      <LoaderCircle aria-hidden="true" className={cn("animate-spin text-accent", SIZES[size])} />
      <span className="sr-only">{label}</span>
    </span>
  );
}

/** Placeholder block for content that is still loading. */
export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden="true" className={cn("animate-pulse rounded-md bg-surface-muted", className)} />;
}
