import {
  BookOpen,
  Bot,
  Building2,
  ChartColumn,
  LayoutDashboard,
  LifeBuoy,
  MessageCircle,
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
}

export interface NavItem {
  id: string;
  label: string;
  href: string;
  icon: LucideIcon;
  children?: NavChild[];
  badgeKey?: NavBadgeKey;
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
        ],
      },
      { id: "cases", label: "Cases & Escalations", href: "/cases", icon: LifeBuoy },
    ],
  },
  {
    id: "operations",
    label: "Business Operations",
    items: [
      { id: "knowledge", label: "Knowledge Base", href: "/knowledge", icon: BookOpen },
      { id: "workflows", label: "Workflows", href: "/workflows", icon: Workflow },
      { id: "departments", label: "Departments", href: "/departments", icon: Building2 },
      { id: "employees", label: "Employees", href: "/employees", icon: Users },
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

/** URL segment -> breadcrumb label. Unknown segments fall back to a humanised form. */
export const ROUTE_LABELS: Record<string, string> = {
  dashboard: "Overview",
  agents: "AI Agents",
  communication: "Communication Center",
  calls: "Calls",
  sms: "SMS Inbox",
  conversations: "Conversations",
  cases: "Cases & Escalations",
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
};

export function isRouteActive(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}
