"use client";

import { X } from "lucide-react";
import { useEffect, useRef } from "react";
import { BusinessSwitcher } from "@/components/layout/BusinessSwitcher";
import type { NavBadges } from "@/components/navigation/NavigationGroup";
import { SidebarNav } from "@/components/navigation/SidebarNav";

interface MobileNavigationProps {
  open: boolean;
  onClose: () => void;
  badges: NavBadges;
}

/**
 * Slide-in navigation for phones. Uses a native <dialog> so focus is trapped
 * inside while open and Escape closes it.
 */
export function MobileNavigation({ open, onClose, badges }: MobileNavigationProps) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      aria-label="Navigation menu"
      onClose={onClose}
      onClick={(event) => {
        if (event.target === ref.current) onClose();
      }}
      className="fixed inset-y-0 left-0 m-0 h-dvh max-h-none w-72 max-w-[85vw] overflow-hidden border-r border-sidebar-border bg-sidebar p-0 text-sidebar-text md:hidden"
    >
      <div className="flex h-full flex-col">
        <div className="flex items-center gap-2 border-b border-sidebar-border px-4 py-4">
          <div className="min-w-0 flex-1">
            <BusinessSwitcher collapsed={false} />
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close navigation menu"
            className="rounded-md p-1.5 text-sidebar-text hover:bg-sidebar-hover hover:text-sidebar-text-strong"
          >
            <X aria-hidden="true" className="size-5" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-3 py-5">
          <SidebarNav collapsed={false} badges={badges} onNavigate={onClose} />
        </div>
      </div>
    </dialog>
  );
}
