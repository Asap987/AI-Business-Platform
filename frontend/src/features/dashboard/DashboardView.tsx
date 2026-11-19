"use client";

import { AgentStatusCard } from "@/features/dashboard/AgentStatusCard";
import { CaseOverviewCard } from "@/features/dashboard/CaseOverviewCard";
import { CommunicationActivity } from "@/features/dashboard/CommunicationActivity";
import { DepartmentActivityCard } from "@/features/dashboard/DepartmentActivityCard";
import { KpiGrid } from "@/features/dashboard/KpiGrid";
import { WelcomeSection } from "@/features/dashboard/WelcomeSection";

/** Dashboard layout. Each section loads its own data and handles its own states. */
export function DashboardView() {
  return (
    <>
      <WelcomeSection />
      <KpiGrid />
      <div className="mb-6">
        <CommunicationActivity />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <CaseOverviewCard />
        <DepartmentActivityCard />
      </div>
      <div className="mt-6">
        <AgentStatusCard />
      </div>
    </>
  );
}
