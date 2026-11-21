import { API_BASE_URL, API_PREFIX } from "@/lib/config";
import { Downsampler, Framer, PcmDecoder, level, pcmRate } from "@/lib/voice/pcm";

export type CallPhase = "idle" | "connecting" | "live" | "ended";
export type ServerState = "listening" | "thinking" | "speaking" | "escalating" | "ended";

export interface TranscriptLine {
  id: number;
  speaker: "customer" | "assistant";
  text: string;
  interrupted?: boolean;
}

export interface CallEvents {
  onPhase(phase: CallPhase): void;
  onState(state: ServerState): void;
  onTranscript(line: TranscriptLine): void;
  onLevel(level: number): void;
  onHandover(): void;
  onError(message: string): void;
  onSpeaking(speaking: boolean): void;
}

const ERROR_TEXT: Record<string, string> = {
  voice_not_enabled: "Live voice isn't switched on for this server yet.",
  no_voice_configured: "No voice has been chosen for the assistant yet.",
  too_many_calls: "Too many calls are running right now. Try again in a moment.",
  ai_disabled_by_business: "AI providers are switched off for your business (Settings → Privacy & AI).",
};

export function describeError(code: string): string {
  if (code.startsWith("speech_unavailable")) return "Speech recognition isn't available right now.";
  return ERROR_TEXT[code] ?? "The call couldn't continue.";
}

export function callUrl(): string {
  return `${API_BASE_URL.replace(/^http/, "ws")}${API_PREFIX}/voice/test-call`;
}

function micErrorText(error: unknown): string {
  const name = error instanceof DOMException ? error.name : "";
  if (name === "NotAllowedError" || name === "SecurityError") return "Microphone access was blocked. Allow it in your browser's address bar, then try again.";
  if (name === "NotFoundError" || name === "OverconstrainedError") return "No microphone was found.";
  if (name === "NotReadableError") return "The microphone is in use by another app.";
  return "The microphone couldn't be started.";
}

/** Plays streamed PCM chunks gaplessly and can drop everything that is queued (barge-in). */
class Player {
  private context: AudioContext | null = null;
  private decoder = new PcmDecoder();
  private nextTime = 0;
  private active = new Set<AudioBufferSourceNode>();

  constructor(
    private readonly rate: number,
    private readonly onSpeaking: (speaking: boolean) => void,
  ) {}

  enqueue(bytes: Uint8Array): void {
    const samples = this.decoder.decode(bytes);
    if (samples.length === 0) return;
    this.context ??= new AudioContext();
    const ctx = this.context;
    if (ctx.state === "suspended") void ctx.resume();
    const buffer = ctx.createBuffer(1, samples.length, this.rate);
    buffer.copyToChannel(new Float32Array(samples), 0);
    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(ctx.destination);
    this.nextTime = Math.max(this.nextTime, ctx.currentTime + 0.05);
    source.start(this.nextTime);
    this.nextTime += buffer.duration;
    this.active.add(source);
    this.onSpeaking(true);
    source.onended = () => {
      this.active.delete(source);
      if (this.active.size === 0) this.onSpeaking(false);
    };
  }

  /** Stop what is playing and discard what is queued. */
  flush(): void {
    for (const source of this.active) {
      source.onended = null;
      try {
        source.stop();
      } catch {
        /* already stopped */
      }
    }
    this.active.clear();
    this.decoder.reset();
    this.nextTime = 0;
    this.onSpeaking(false);
  }

  async close(): Promise<void> {
    this.flush();
    await this.context?.close().catch(() => undefined);
    this.context = null;
  }
}

export class VoiceCall {
  private ws: WebSocket | null = null;
  private stream: MediaStream | null = null;
  private capture: AudioContext | null = null;
  private player: Player | null = null;
  private phase: CallPhase = "idle";
  private lineId = 0;
  private stopped = false;

  constructor(private readonly events: CallEvents) {}

  async start(): Promise<void> {
    if (this.phase !== "idle" && this.phase !== "ended") return;
    this.stopped = false;
    this.setPhase("connecting");
    try {
      // Echo cancellation matters: without it the assistant's own voice is heard as the customer and cuts it off.
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
    } catch (error) {
      this.fail(micErrorText(error));
      return;
    }
    if (this.stopped) return void this.release();
    const ws = new WebSocket(callUrl());
    ws.binaryType = "arraybuffer";
    this.ws = ws;
    ws.onmessage = (e) => void this.onMessage(e);
    ws.onclose = (e) => {
      if (this.phase === "ended") return;
      if (this.phase === "connecting") this.fail(e.code === 1008 ? "The call was refused. You may not have permission, or your session expired." : "Couldn't reach the voice service.");
      else this.finish();
    };
    ws.onerror = () => undefined; // onclose follows and carries the outcome
  }

  async stop(): Promise<void> {
    this.stopped = true;
    if (this.ws?.readyState === WebSocket.OPEN) {
      try {
        this.ws.send(JSON.stringify({ type: "end" }));
      } catch {
        /* closing anyway */
      }
    }
    this.finish();
  }

  // ---- internals ---------------------------------------------------------
  private setPhase(phase: CallPhase): void {
    this.phase = phase;
    this.events.onPhase(phase);
  }

  private fail(message: string): void {
    this.events.onError(message);
    this.finish();
  }

  private finish(): void {
    if (this.phase === "ended") return;
    this.setPhase("ended");
    this.events.onLevel(0);
    try {
      this.ws?.close();
    } catch {
      /* already closed */
    }
    this.ws = null;
    this.release();
  }

  private release(): void {
    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = null;
    void this.capture?.close().catch(() => undefined);
    this.capture = null;
    void this.player?.close();
    this.player = null;
  }

  private async onMessage(event: MessageEvent): Promise<void> {
    if (typeof event.data !== "string") {
      this.player?.enqueue(new Uint8Array(event.data as ArrayBuffer));
      return;
    }
    let msg: Record<string, unknown>;
    try {
      msg = JSON.parse(event.data) as Record<string, unknown>;
    } catch {
      return;
    }
    switch (msg.type) {
      case "ready": {
        const rate = pcmRate(String(msg.output_format ?? ""));
        if (rate === null) return this.fail("The server's audio format isn't supported by this page.");
        this.player = new Player(rate, (s) => this.events.onSpeaking(s));
        try {
          await this.startCapture();
        } catch (error) {
          return this.fail(error instanceof Error && error.message ? "The microphone couldn't be started." : micErrorText(error));
        }
        this.setPhase("live");
        break;
      }
      case "state":
        this.events.onState(msg.state as ServerState);
        break;
      case "transcript":
        this.events.onTranscript({ id: ++this.lineId, speaker: msg.speaker as "customer" | "assistant", text: String(msg.text ?? ""), interrupted: Boolean(msg.interrupted) });
        break;
      case "interrupted":
        this.player?.flush();
        break;
      case "handover":
        this.events.onHandover();
        break;
      case "error":
        this.fail(describeError(String(msg.code ?? "")));
        break;
    }
  }

  private async startCapture(): Promise<void> {
    if (!this.stream) throw new Error("no stream");
    const ctx = new AudioContext();
    this.capture = ctx;
    await ctx.audioWorklet.addModule("/pcm-capture-worklet.js");
    const source = ctx.createMediaStreamSource(this.stream);
    const node = new AudioWorkletNode(ctx, "pcm-capture", { numberOfInputs: 1, numberOfOutputs: 0 });
    const down = new Downsampler(ctx.sampleRate, 16000);
    const framer = new Framer(1600);
    node.port.onmessage = (e: MessageEvent<Float32Array>) => {
      this.events.onLevel(level(e.data));
      if (this.ws?.readyState !== WebSocket.OPEN) return;
      for (const frame of framer.push(down.push(e.data))) this.ws.send(frame);
    };
    source.connect(node);
    if (ctx.state === "suspended") await ctx.resume();
  }
}
