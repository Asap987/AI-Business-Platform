import {
  BookOpen,
  Bot,
  Building2,
  ChartColumn,
  CircleHelp,
  LifeBuoy,
  MessageCircle,
  MessageSquareText,
  PhoneCall,
  Plug,
  Settings,
  User,
  UserCog,
  Users,
  Workflow,
  type LucideIcon,
} from "lucide-react";

export type ModuleKey =
  | "agents"
  | "calls"
  | "sms"
  | "conversations"
  | "cases"
  | "knowledge"
  | "workflows"
  | "departments"
  | "employees"
  | "analytics"
  | "integrations"
  | "profile"
  | "account"
  | "business"
  | "help";

export interface ModuleInfo {
  title: string;
  description: string;
  icon: LucideIcon;
  /** What the finished module will cover, shown on its placeholder page. */
  planned: string[];
}

/** Content for the "under development" pages of modules not built yet. */
export const MODULES: Record<ModuleKey, ModuleInfo> = {
  agents: {
    title: "AI Agents",
    description: "Create and manage the AI assistants that answer your customers.",
    icon: Bot,
    planned: [
      "Create, configure and pause agents per department",
      "Choose which channels each agent handles",
      "Review agent activity and hand-offs to staff",
    ],
  },
  calls: {
    title: "Calls",
    description: "Customer telephone calls handled by your AI agents and staff.",
    icon: PhoneCall,
    planned: ["Call history with outcomes and summaries", "Live call status", "Escalate a call to a case"],
  },
  sms: {
    title: "SMS Inbox",
    description: "Text-message conversations with your customers.",
    icon: MessageSquareText,
    planned: ["Unified SMS inbox with unread counts", "Reply as staff or let an agent respond", "Convert a thread into a case"],
  },
  conversations: {
    title: "Conversations",
    description: "Every customer conversation across all channels in one place.",
    icon: MessageCircle,
    planned: ["Filter by channel, status and agent", "Full message history and summaries", "Link conversations to customers and cases"],
  },
  cases: {
    title: "Cases & Escalations",
    description: "Customer problems that need resolution, and who is working on them.",
    icon: LifeBuoy,
    planned: ["Case queue by status and priority", "Assign to employees or agents", "Escalate to the right department and track resolution"],
  },
  knowledge: {
    title: "Knowledge Base",
    description: "The business information your AI agents rely on to answer correctly.",
    icon: BookOpen,
    planned: ["Upload and organise reference documents", "Control which agents can use which content", "Review answers an agent could not give"],
  },
  workflows: {
    title: "Workflows",
    description: "Automated steps for routing and resolving customer issues.",
    icon: Workflow,
    planned: ["Define routing and escalation rules", "Trigger actions from conversation outcomes", "Monitor workflow runs"],
  },
  departments: {
    title: "Departments",
    description: "The teams in your business, such as Technical, Finance and Delivery.",
    icon: Building2,
    planned: ["Create and edit departments", "See workload and pending requests per department", "Assign staff and agents"],
  },
  employees: {
    title: "Employees",
    description: "Your staff and the departments they belong to.",
    icon: Users,
    planned: ["Employee directory", "Department assignments", "Invite staff to the Control Center"],
  },
  analytics: {
    title: "Analytics & Reports",
    description: "How your customer communication and problem resolution are performing.",
    icon: ChartColumn,
    planned: ["Resolution rate and response-time trends", "Volume by channel and department", "Exportable reports"],
  },
  integrations: {
    title: "Integrations",
    description: "Connect telephony, messaging and the tools your business already uses.",
    icon: Plug,
    planned: ["Telephone and SMS providers", "Business systems such as CRM and ticketing", "Connection health and credentials"],
  },
  profile: {
    title: "My Profile",
    description: "Your personal details as they appear in the Control Center.",
    icon: User,
    planned: ["Edit your name and contact details", "Notification preferences"],
  },
  account: {
    title: "Account Settings",
    description: "Sign-in and security settings for your account.",
    icon: UserCog,
    planned: ["Change password", "Active sessions", "Sign-in security options"],
  },
  business: {
    title: "Business Settings",
    description: "Settings that apply to your whole business.",
    icon: Settings,
    planned: ["Business name, industry and time zone", "Roles and permissions", "Team management"],
  },
  help: {
    title: "Help & Support",
    description: "Get help using the Control Center.",
    icon: CircleHelp,
    planned: ["Guides for each module", "Contact support", "Report a problem"],
  },
};
