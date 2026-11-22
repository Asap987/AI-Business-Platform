"use client";

import { Bot } from "lucide-react";
import Link from "next/link";
import { useAgents } from "@/features/dashboard/api";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { ButtonLink } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/LoadingSpinner";
import { ResourceView } from "@/components/ui/ResourceView";
import { formatRelativeTime, humanize } from "@/lib/utils";

export function AgentStatusCard() {
  const resource = useAgents();

  return (
    <Card>
      <CardHeader
        title="AI agent status"
        description="Whether each agent is running and where it's answering customers."
        action={
          <Link href="/agents" className="text-sm font-medium text-accent-strong hover:underline">
            Manage agents
          </Link>
        }
      />
      <ResourceView
        resource={resource}
        isEmpty={(data) => data.items.length === 0}
        skeleton={
          <div className="space-y-3 p-5">
            <Skeleton className="h-14" />
            <Skeleton className="h-14" />
          </div>
        }
        empty={
          <EmptyState
            compact
            icon={Bot}
            title="No AI agents yet"
            description="Create your first agent to start answering customer calls and messages."
            action={
              <ButtonLink href="/agents" size="sm">
                Go to AI agents
              </ButtonLink>
            }
          />
        }
      >
        {(data) => (
          <ul className="divide-y divide-border">
            {data.items.map((agent) => (
              <li key={agent.id} className="flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="truncate text-sm font-semibold text-ink">{agent.name}</span>
                    <StatusBadge status={agent.status} />
                    <Badge tone={agent.configured ? "success" : "warning"}>
                      {agent.configured ? "Configured" : "Needs setup"}
                    </Badge>
                  </div>
                  <p className="mt-1.5 text-sm text-muted">
                    {agent.channels.length > 0
                      ? `Channels: ${agent.channels.map(humanize).join(", ")}`
                      : "No channels enabled"}
                  </p>
                </div>
                <p className="shrink-0 text-sm text-muted">
                  Last activity: {agent.last_activity_at ? formatRelativeTime(agent.last_activity_at) : "none yet"}
                </p>
              </li>
            ))}
          </ul>
        )}
      </ResourceView>
    </Card>
  );
}
