import type { Metadata } from "next";
import { CallbacksView } from "@/features/callbacks/CallbacksView";

export const metadata: Metadata = { title: "Callback requests" };

export default function CallbacksPage() {
  return <CallbacksView />;
}
