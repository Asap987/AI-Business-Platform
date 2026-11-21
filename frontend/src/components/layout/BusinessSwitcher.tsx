"use client";

import { Check, ChevronsUpDown } from "lucide-react";
import { useState } from "react";
import { Dropdown } from "@/components/ui/Dropdown";
import { Tooltip } from "@/components/ui/Tooltip";
import { ApiError } from "@/lib/api";
import { KasoraMark } from "@/components/brand/KasoraMark";
import { APP_NAME } from "@/lib/config";
import { cn } from "@/lib/utils";
import { useAuth } from "@/providers/AuthProvider";

/** Brand mark plus the active business, with a switcher only for multi-business accounts. */
export function BusinessSwitcher({ collapsed }: { collapsed: boolean }) {
  const { business, businesses, switchBusiness } = useAuth();
  const [switchError, setSwitchError] = useState<string | null>(null);

  const canSwitch = businesses.length > 1;
  const name = business?.name ?? "Your business";

  const mark = (
    <span
      aria-hidden="true"
      className="flex size-9 shrink-0 items-center justify-center text-sidebar-text-strong"
    >
      <KasoraMark className="size-8" />
    </span>
  );

  if (collapsed) {
    return (
      <div className="flex justify-center">
        <Tooltip content={name} side="right">
          <span className="inline-flex" aria-label={`${APP_NAME}, ${name}`} role="img">
            {mark}
          </span>
        </Tooltip>
      </div>
    );
  }

  const text = (
    <span className="min-w-0 text-left">
      <span className="block truncate text-sm font-semibold text-sidebar-text-strong">{APP_NAME}</span>
      <span className="block truncate text-xs text-sidebar-muted">{name}</span>
    </span>
  );

  if (!canSwitch) {
    return (
      <div className="flex items-center gap-3 px-1">
        {mark}
        {text}
      </div>
    );
  }

  return (
    <div>
      <Dropdown
        label="Switch business"
        align="left"
        panelClassName="w-60"
        header={<p className="text-xs font-semibold uppercase tracking-wide text-muted">Switch business</p>}
        items={businesses.map((b) => ({
          id: b.id,
          label: b.name,
          icon:
            b.id === business?.id ? (
              <Check aria-hidden="true" className="size-4 text-accent-strong" />
            ) : (
              <span aria-hidden="true" className="size-4" />
            ),
          onSelect: () => {
            setSwitchError(null);
            switchBusiness(b.id).catch((error: unknown) => {
              setSwitchError(
                error instanceof ApiError && error.kind === "forbidden"
                  ? "You don't have access to that business."
                  : "Couldn't switch business. Please try again.",
              );
            });
          },
        }))}
        renderTrigger={(props) => (
          <button
            type="button"
            {...props}
            className={cn(
              "flex w-full items-center gap-3 rounded-lg px-1 py-1 transition-colors hover:bg-sidebar-hover",
            )}
          >
            {mark}
            {text}
            <ChevronsUpDown aria-hidden="true" className="ml-auto size-4 shrink-0 text-sidebar-muted" />
            <span className="sr-only">Switch business. Current: {name}</span>
          </button>
        )}
      />
      {switchError ? (
        <p role="alert" className="mt-2 px-1 text-xs text-danger-soft">
          {switchError}
        </p>
      ) : null}
    </div>
  );
}
