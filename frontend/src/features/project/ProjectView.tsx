"use client";

import { useState } from "react";
import { ErrorMessage } from "@/components/ui/ErrorMessage";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/LoadingSpinner";
import { ResourceView } from "@/components/ui/ResourceView";
import { TabPanel, Tabs } from "@/components/ui/Tabs";
import { useApiResource } from "@/hooks/useApiResource";
import { formatRelativeTime } from "@/lib/utils";
import type { ProjectData } from "@/types/project";
import { ExternalTab, FinanceTab } from "./ExternalFinanceTabs";
import { ModulesTab, OverviewTab } from "./OverviewTab";
import { RoadmapTab } from "./RoadmapTab";
import { TasksTab } from "./TasksTab";
import { TestsTab } from "./TestsTab";

const PREFIX = "project";

/** Internal build tracker. The server answers 404 to anyone who is not a platform administrator. */
export function ProjectView() {
  const resource = useApiResource<ProjectData>("/platform/project");
  const [tab, setTab] = useState("overview");
  const [module, setModule] = useState("");
  const go = (id: string) => setTab(id);
  // Keep showing the last good data while a refresh runs, so a save does not blank the page or reset filters.
  const [last, setLast] = useState<ProjectData | null>(null);
  if (resource.data && resource.data !== last) setLast(resource.data);

  return (
    <>
      <PageHeader
        title="Project progress"
        description="Internal view of the Kasora AI build. Progress is the weight of completed, evidenced tasks, never a guess."
        actions={<Button variant="secondary" onClick={resource.reload}>Refresh</Button>}
      />
      {last && resource.status === "error" && resource.error ? <div className="mb-3"><ErrorMessage error={resource.error} onRetry={resource.reload} compact /></div> : null}
      <ResourceView
        resource={last ? { ...resource, status: "success", data: last } : resource}
        compact={false}
        skeleton={<Skeleton className="h-64" />}
        empty={<EmptyState title="Nothing tracked yet" description="Load the tasks with python scripts/seed_project.py from the backend folder." />}
      >
        {(data) => {
          const tabs = [
            { id: "overview", label: "Overview" },
            { id: "modules", label: "Modules", count: data.modules.length },
            { id: "tasks", label: "Tasks", count: data.tasks.length },
            { id: "roadmap", label: "Roadmap" },
            { id: "tests", label: "Tests" },
            { id: "external", label: "External", count: data.external.filter((e) => e.category !== "completed").length },
            { id: "finance", label: "Finance & launch" },
          ];
          return (
            <>
              <p className="mb-3 text-xs text-muted">Generated {formatRelativeTime(data.generated_at)}{data.git_head ? ` · code at commit ${data.git_head}` : ""}</p>
              <Tabs tabs={tabs} value={tab} onChange={go} idPrefix={PREFIX} label="Project sections" />
              <div className="pt-6">
                <TabPanel idPrefix={PREFIX} id={tab}>
                  {tab === "overview" ? <OverviewTab data={data} goto={go} /> : null}
                  {tab === "modules" ? <ModulesTab data={data} openModule={(k) => { setModule(k); go("tasks"); }} /> : null}
                  {tab === "tasks" ? <TasksTab key={module} data={data} reload={resource.reload} initialModule={module} /> : null}
                  {tab === "roadmap" ? <RoadmapTab data={data} /> : null}
                  {tab === "tests" ? <TestsTab data={data} /> : null}
                  {tab === "external" ? <ExternalTab data={data} reload={resource.reload} /> : null}
                  {tab === "finance" ? <FinanceTab data={data} reload={resource.reload} /> : null}
                </TabPanel>
              </div>
            </>
          );
        }}
      </ResourceView>
    </>
  );
}
