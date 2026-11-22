import type { Metadata } from "next";
import { ProjectView } from "@/features/project/ProjectView";

export const metadata: Metadata = { title: "Project progress" };

export default function ProjectPage() {
  return <ProjectView />;
}
