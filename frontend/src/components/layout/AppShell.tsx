"use client";

import { useState, type ReactNode } from "react";
import { VerifyEmailBanner } from "@/components/layout/VerifyEmailBanner";
import { MobileNavigation } from "@/components/layout/MobileNavigation";
import { Sidebar } from "@/components/layout/Sidebar";
import { Topbar } from "@/components/layout/Topbar";
import { useNotifications } from "@/hooks/useNotifications";
import { useSidebarCollapsed } from "@/hooks/useSidebarCollapsed";

/**
 * The frame shared by every authenticated page: sidebar, top bar, mobile
 * drawer and the main content area.
 */
export function AppShell({ children }: { children: ReactNode }) {
  const { collapsed, toggle } = useSidebarCollapsed();
  const [mobileOpen, setMobileOpen] = useState(false);
  const notifications = useNotifications();

  const unreadConversations =
    notifications.status === "success" ? (notifications.data?.unread_conversations ?? 0) : 0;
  const badges = { unread_conversations: unreadConversations };

  return (
    <div className="flex min-h-dvh">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded-lg focus:bg-primary focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:text-on-primary"
      >
        Skip to main content
      </a>

      <Sidebar collapsed={collapsed} badges={badges} />
      <MobileNavigation open={mobileOpen} onClose={() => setMobileOpen(false)} badges={badges} />

      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar
          sidebarCollapsed={collapsed}
          onToggleSidebar={toggle}
          onOpenMobileNav={() => setMobileOpen(true)}
          notifications={notifications}
        />
        <VerifyEmailBanner />
        <main id="main-content" tabIndex={-1} className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 outline-none md:px-8 md:py-8">
          {children}
        </main>
      </div>
    </div>
  );
}
