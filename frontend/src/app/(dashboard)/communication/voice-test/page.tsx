import type { Metadata } from "next";
import { VoiceTestView } from "@/features/voice/VoiceTestView";

export const metadata: Metadata = { title: "Voice test call" };

export default function VoiceTestPage() {
  return <VoiceTestView />;
}
