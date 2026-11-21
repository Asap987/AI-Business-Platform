"use client";

import { Mic, PhoneOff } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { FormError } from "@/components/ui/ErrorMessage";
import { Skeleton } from "@/components/ui/LoadingSpinner";
import { ResourceView } from "@/components/ui/ResourceView";
import { useApiResource } from "@/hooks/useApiResource";
import { usePermission } from "@/hooks/usePermission";
import { VoiceCall, type CallPhase, type ServerState, type TranscriptLine } from "@/lib/voice/client";

interface VoiceStatus {
  available: boolean;
  missing: string[];
  disabled_providers: string[];
}

const STATE_LABEL: Record<ServerState, string> = {
  listening: "Listening",
  thinking: "Thinking",
  speaking: "Speaking",
  escalating: "Handed to a person",
  ended: "Ended",
};

function Call() {
  const [phase, setPhase] = useState<CallPhase>("idle");
  const [state, setState] = useState<ServerState>("listening");
  const [speaking, setSpeaking] = useState(false);
  const [lines, setLines] = useState<TranscriptLine[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [handover, setHandover] = useState(false);
  const meter = useRef<HTMLDivElement>(null);
  const call = useRef<VoiceCall | null>(null);

  useEffect(() => () => void call.current?.stop(), []); // leaving the page hangs up and releases the microphone

  function begin() {
    setLines([]);
    setError(null);
    setHandover(false);
    setState("listening");
    call.current = new VoiceCall({
      onPhase: setPhase,
      onState: setState,
      onTranscript: (line) => setLines((prev) => [...prev, line]),
      onLevel: (v) => {
        if (meter.current) meter.current.style.width = `${Math.round(Math.min(1, v * 4) * 100)}%`;
      },
      onHandover: () => setHandover(true),
      onError: setError,
      onSpeaking: setSpeaking,
    });
    void call.current.start();
  }

  const active = phase === "connecting" || phase === "live";
  const label = phase === "connecting" ? "Connecting" : phase === "live" ? (speaking ? "Speaking" : STATE_LABEL[state] ?? "Listening") : phase === "ended" ? "Call ended" : "Not in a call";

  return (
    <>
      <Card className="mb-6 p-5">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-sm text-muted">Status</p>
            <p className="text-lg font-semibold text-ink" role="status" aria-live="polite" data-testid="call-status">{label}</p>
          </div>
          <div className="flex items-center gap-3">
            {active ? (
              <Button variant="danger" onClick={() => void call.current?.stop()}>
                <PhoneOff aria-hidden="true" className="size-4" />
                End call
              </Button>
            ) : (
              <Button onClick={begin}>
                <Mic aria-hidden="true" className="size-4" />
                Start test call
              </Button>
            )}
          </div>
        </div>
        <div className="mt-4" aria-hidden={!active}>
          <p className="mb-1 text-xs text-muted">Microphone level</p>
          <div className="h-2 overflow-hidden rounded-full bg-surface-muted">
            <div ref={meter} className="h-full w-0 bg-accent transition-[width] duration-75" />
          </div>
        </div>
        <p className="mt-4 text-sm text-muted">
          Use headphones if you can. If the assistant&apos;s voice reaches your microphone it hears itself and keeps interrupting. Nothing from the call is saved.
        </p>
      </Card>

      {error ? <div className="mb-4"><FormError message={error} /></div> : null}
      {handover ? (
        <div className="mb-4 rounded-lg border border-border bg-surface-muted p-3 text-sm text-ink" role="status">
          The assistant handed this call to a person. In a real call, a team member would take over now.
        </div>
      ) : null}

      <Card className="p-5">
        <h2 className="mb-3 text-base font-semibold text-ink">Conversation</h2>
        {lines.length === 0 ? (
          <p className="text-sm text-muted">{active ? "Say something, for example: “What time do you open?”" : "Start a test call to talk to the assistant."}</p>
        ) : (
          <ul className="space-y-3" aria-live="polite" data-testid="transcript">
            {lines.map((l) => (
              <li key={l.id} className={l.speaker === "customer" ? "text-right" : ""}>
                <span className="mb-0.5 block text-xs text-muted">{l.speaker === "customer" ? "You" : "Assistant"}{l.interrupted ? " (interrupted)" : ""}</span>
                <span className={`inline-block max-w-[85%] rounded-lg px-3 py-2 text-sm ${l.speaker === "customer" ? "bg-accent text-white" : "bg-surface-muted text-ink"}`}>{l.text}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}

export function VoiceTestView() {
  const allowed = usePermission("voice:use");
  const status = useApiResource<VoiceStatus>(allowed ? "/voice/status" : null);

  if (!allowed) {
    return (
      <>
        <PageHeader title="Voice test call" description="Talk to your AI assistant from this browser." />
        <Card><EmptyState icon={Mic} title="Permission denied" description="Your role can't start test calls. Ask an administrator." /></Card>
      </>
    );
  }
  return (
    <>
      <PageHeader title="Voice test call" description="Talk to your AI assistant from this browser to check how it answers. It can use your knowledge base." />
      <ResourceView resource={status} compact={false} skeleton={<Skeleton className="h-32" />}>
        {(s) =>
          s.available ? (
            <Call />
          ) : (
            <Card>
              <EmptyState
                icon={Mic}
                title="Live voice isn't switched on yet"
                description={`Ask whoever runs the server to set: ${s.missing.join(", ")}. Live voice calls paid AI services, so it stays off until then.`}
              />
            </Card>
          )
        }
      </ResourceView>
    </>
  );
}
