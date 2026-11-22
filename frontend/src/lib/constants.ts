import {
  BookOpen,
  Bot,
  Building2,
  ChartColumn,
  LayoutDashboard,
  Contact,
  ClipboardList,
  LifeBuoy,
  MessageCircle,
  Mic,
  MessageSquareText,
  MessagesSquare,
  PhoneCall,
  Plug,
  Settings,
  Users,
  Workflow,
  type LucideIcon,
} from "lucide-react";

/** Counters the shell can show as badges, keyed by NavItem.badgeKey. */
export type NavBadgeKey = "unread_conversations";

export interface NavChild {
  id: string;
  label: string;
  href: string;
  icon: LucideIcon;
  /** Permission needed to see this link (UX only: the backend enforces). Omit for everyone. */
  permission?: string;
}

export interface NavItem {
  id: string;
  label: string;
  href: string;
  icon: LucideIcon;
  children?: NavChild[];
  badgeKey?: NavBadgeKey;
  /** Permission needed to see this item (UX only: the backend enforces). Omit for everyone. */
  permission?: string;
}

export interface NavGroup {
  id: string;
  label: string;
  items: NavItem[];
}

export const NAV_GROUPS: NavGroup[] = [
  {
    id: "main",
    label: "Main",
    items: [
      { id: "overview", label: "Overview", href: "/dashboard", icon: LayoutDashboard },
      { id: "agents", label: "AI Agents", href: "/agents", icon: Bot },
      {
        id: "communication",
        label: "Communication Center",
        href: "/communication",
        icon: MessagesSquare,
        badgeKey: "unread_conversations",
        children: [
          { id: "calls", label: "Calls", href: "/communication/calls", icon: PhoneCall },
          { id: "sms", label: "SMS Inbox", href: "/communication/sms", icon: MessageSquareText },
          { id: "conversations", label: "Conversations", href: "/communication/conversations", icon: MessageCircle },
          { id: "voice-test", label: "Voice test", href: "/communication/voice-test", icon: Mic, permission: "voice:use" },
        ],
      },
      { id: "cases", label: "Cases & Escalations", href: "/cases", icon: LifeBuoy, permission: "cases:read" },
    ],
  },
  {
    id: "operations",
    label: "Business Operations",
    items: [
      { id: "knowledge", label: "Knowledge Base", href: "/knowledge", icon: BookOpen, permission: "knowledge:read" },
      { id: "workflows", label: "Workflows", href: "/workflows", icon: Workflow },
      { id: "customers", label: "Customers", href: "/customers", icon: Contact, permission: "customers:read" },
      { id: "departments", label: "Departments", href: "/departments", icon: Building2, permission: "departments:read" },
      { id: "employees", label: "Employees", href: "/employees", icon: Users, permission: "employees:read" },
    ],
  },
  {
    id: "management",
    label: "Management",
    items: [
      { id: "analytics", label: "Analytics & Reports", href: "/analytics", icon: ChartColumn },
      { id: "integrations", label: "Integrations", href: "/integrations", icon: Plug },
      { id: "settings", label: "Settings", href: "/settings", icon: Settings },
    ],
  },
];

/** Shown only to platform administrators (the server decides; see usePlatformAccess). */
export const PLATFORM_GROUP: NavGroup = {
  id: "platform",
  label: "Platform",
  items: [{ id: "project", label: "Project progress", href: "/platform/project", icon: ClipboardList }],
};

/** URL segment -> breadcrumb label. Unknown segments fall back to a humanised form. */
export const ROUTE_LABELS: Record<string, string> = {
  dashboard: "Overview",
  agents: "AI Agents",
  communication: "Communication Center",
  calls: "Calls",
  sms: "SMS Inbox",
  conversations: "Conversations",
  "voice-test": "Voice test call",
  cases: "Cases & Escalations",
  customers: "Customers",
  knowledge: "Knowledge Base",
  workflows: "Workflows",
  departments: "Departments",
  employees: "Employees",
  analytics: "Analytics & Reports",
  integrations: "Integrations",
  settings: "Settings",
  profile: "My Profile",
  account: "Account Settings",
  business: "Business Settings",
  help: "Help & Support",
  platform: "Platform",
  project: "Project progress",
};

export function isRouteActive(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}
