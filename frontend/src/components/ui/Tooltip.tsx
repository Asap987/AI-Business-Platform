"use client";

import { useId, type ReactNode } from "react";
import { cn } from "@/lib/utils";

interface TooltipProps {
  content: string;
  children: ReactNode;
  side?: "right" | "bottom";
  /** When true the tooltip is never shown (e.g. sidebar is expanded). */
  disabled?: boolean;
  className?: string;
}

const SIDES = {
  right: "left-full top-1/2 ml-2 -translate-y-1/2",
  bottom: "left-1/2 top-full mt-2 -translate-x-1/2",
} as const;

/**
 * Shows on hover and on keyboard focus, so it never depends on a mouse.
 * Touch users get the same information from the visible label or the
 * element's own aria-label; the tooltip is a convenience, not the only source.
 */
export function Tooltip({ content, children, side = "bottom", disabled = false, className }: TooltipProps) {
  const id = useId();
  if (disabled) return <>{children}</>;

  return (
    <span className={cn("group/tooltip relative inline-flex", className)} aria-describedby={id}>
      {children}
      <span
        id={id}
        role="tooltip"
        className={cn(
          "pointer-events-none absolute z-50 whitespace-nowrap rounded-md bg-primary px-2 py-1 text-xs font-medium text-on-primary opacity-0 shadow-pop transition-opacity",
          "group-hover/tooltip:opacity-100 group-focus-within/tooltip:opacity-100",
          SIDES[side],
        )}
      >
        {content}
      </span>
    </span>
  );
}
