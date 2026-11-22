import type { ReactNode } from "react";
import { KasoraMark } from "@/components/brand/KasoraMark";
import { GuestGuard } from "@/components/layout/AuthGuard";
import { APP_NAME } from "@/lib/config";

export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <GuestGuard>
      <div className="grid min-h-dvh lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
        <aside className="hidden flex-col justify-between bg-sidebar p-12 text-sidebar-text lg:flex">
          <div className="flex items-center gap-3">
            <KasoraMark animated className="size-12 text-sidebar-text-strong" />
            <span className="text-lg font-semibold text-sidebar-text-strong">{APP_NAME}</span>
          </div>
          <div>
            <p className="max-w-md text-3xl font-semibold leading-tight tracking-tight text-sidebar-text-strong">
              Every customer call and message, handled and resolved.
            </p>
            <p className="mt-4 max-w-md text-base text-sidebar-text">
              AI assistants answer your customers, route problems to the right department, and keep your team on top of
              every open case.
            </p>
          </div>
          <p className="text-sm text-sidebar-muted">AI-powered business communication and problem resolution.</p>
        </aside>

        <main className="flex items-center justify-center bg-surface px-4 py-10 sm:px-8">
          <div className="w-full max-w-md">
            <div className="mb-8 flex items-center gap-3 lg:hidden">
              <KasoraMark animated className="size-10 text-ink" />
              <span className="text-base font-semibold text-ink">{APP_NAME}</span>
            </div>
            {children}
          </div>
        </main>
      </div>
    </GuestGuard>
  );
}
