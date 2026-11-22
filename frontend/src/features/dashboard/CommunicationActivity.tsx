"use client";

import { Inbox } from "lucide-react";
import Link from "next/link";
import { useId, useState } from "react";
import { useRecentConversations } from "@/features/dashboard/api";
import { Card, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/LoadingSpinner";
import { ResourceView } from "@/components/ui/ResourceView";
import { StatusBadge } from "@/components/ui/Badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/Table";
import { TabPanel, Tabs } from "@/components/ui/Tabs";
import { formatRelativeTime, humanize } from "@/lib/utils";
import type { ConversationSummary } from "@/types/api";

type TabId = "calls" | "sms" | "conversations";

const EMPTY_COPY: Record<TabId, { title: string; description: string }> = {
  calls: { title: "No recent calls", description: "Customer calls will appear here as they come in." },
  sms: { title: "No recent SMS", description: "Text-message conversations will appear here." },
  conversations: { title: "No recent conversations", description: "Customer conversations on any channel will appear here." },
};

function filterFor(tab: TabId, items: ConversationSummary[]): ConversationSummary[] {
  if (tab === "calls") return items.filter((item) => item.channel === "phone");
  if (tab === "sms") return items.filter((item) => item.channel === "sms");
  return items;
}

function ActivityTable({ items }: { items: ConversationSummary[] }) {
  return (
    <Table caption="Recent customer communication">
      <TableHead>
        <tr>
          <TableHeader>Channel</TableHeader>
          <TableHeader>Customer</TableHeader>
          <TableHeader className="hidden md:table-cell">Summary</TableHeader>
          <TableHeader>Status</TableHeader>
          <TableHeader>Time</TableHeader>
        </tr>
      </TableHead>
      <TableBody>
        {items.slice(0, 8).map((item) => (
          <TableRow key={item.id}>
            <TableCell className="whitespace-nowrap">{humanize(item.channel)}</TableCell>
            <TableCell className="font-medium">{item.customer_name}</TableCell>
            <TableCell className="hidden max-w-xs truncate text-muted md:table-cell">
              {item.summary ?? "No summary yet"}
            </TableCell>
            <TableCell>
              <StatusBadge status={item.status} />
            </TableCell>
            <TableCell className="whitespace-nowrap text-muted">{formatRelativeTime(item.started_at)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

export function CommunicationActivity() {
  const resource = useRecentConversations();
  const [tab, setTab] = useState<TabId>("conversations");
  const idPrefix = useId();

  const items = resource.data?.items ?? [];
  const tabs = [
    { id: "calls", label: "Calls", count: resource.status === "success" ? filterFor("calls", items).length : undefined },
    { id: "sms", label: "SMS", count: resource.status === "success" ? filterFor("sms", items).length : undefined },
    { id: "conversations", label: "Conversations", count: resource.status === "success" ? items.length : undefined },
  ];

  return (
    <Card>
      <CardHeader
        title="Communication activity"
        description="The most recent customer calls, texts and conversations."
        action={
          <Link href="/communication/conversations" className="text-sm font-medium text-accent-strong hover:underline">
            View all
          </Link>
        }
      />
      <div className="px-5 pt-2">
        <Tabs tabs={tabs} value={tab} onChange={(id) => setTab(id as TabId)} idPrefix={idPrefix} label="Communication channels" />
      </div>
      <TabPanel idPrefix={idPrefix} id={tab}>
        <ResourceView
          resource={resource}
          isEmpty={(data) => filterFor(tab, data.items).length === 0}
          skeleton={
            <div className="space-y-3 p-5">
              <Skeleton className="h-9" />
              <Skeleton className="h-9" />
              <Skeleton className="h-9" />
            </div>
          }
          empty={<EmptyState compact icon={Inbox} title={EMPTY_COPY[tab].title} description={EMPTY_COPY[tab].description} />}
        >
          {(data) => <ActivityTable items={filterFor(tab, data.items)} />}
        </ResourceView>
      </TabPanel>
    </Card>
  );
}
