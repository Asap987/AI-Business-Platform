/** Pure audio helpers (no browser APIs) so they can be tested in Node. PCM here is signed 16-bit little-endian. */

/** Converts the microphone's sample rate to a target rate by averaging, and emits Int16 samples. */
export class Downsampler {
  private readonly ratio: number;
  private carry: number[] = [];
  private position = 0; // fractional read position into the carried samples

  constructor(
    inputRate: number,
    private readonly outputRate = 16000,
  ) {
    if (!(inputRate > 0) || !(outputRate > 0)) throw new Error("Sample rates must be positive");
    this.ratio = inputRate / outputRate;
  }

  push(samples: Float32Array): Int16Array {
    for (let i = 0; i < samples.length; i++) this.carry.push(samples[i]);
    const out: number[] = [];
    // Each output sample is the average of the input samples it covers (a simple anti-aliasing filter).
    while (this.position + this.ratio <= this.carry.length) {
      const start = Math.floor(this.position);
      const end = Math.min(this.carry.length, Math.max(start + 1, Math.ceil(this.position + this.ratio)));
      let sum = 0;
      for (let i = start; i < end; i++) sum += this.carry[i];
      out.push(floatToInt16(sum / (end - start)));
      this.position += this.ratio;
    }
    const drop = Math.floor(this.position);
    if (drop > 0) {
      this.carry = this.carry.slice(drop);
      this.position -= drop;
    }
    return Int16Array.from(out);
  }
}

export function floatToInt16(value: number): number {
  const clamped = Math.max(-1, Math.min(1, value));
  return clamped < 0 ? Math.round(clamped * 0x8000) : Math.round(clamped * 0x7fff);
}

/** Root-mean-square level of a block, 0..1, for the microphone meter. */
export function level(samples: Float32Array): number {
  if (samples.length === 0) return 0;
  let sum = 0;
  for (let i = 0; i < samples.length; i++) sum += samples[i] * samples[i];
  return Math.min(1, Math.sqrt(sum / samples.length));
}

/** Collects samples into fixed-size frames (default 100 ms at 16 kHz) as little-endian bytes. */
export class Framer {
  private pending: number[] = [];
  constructor(private readonly samplesPerFrame = 1600) {}

  push(samples: Int16Array): Uint8Array[] {
    for (let i = 0; i < samples.length; i++) this.pending.push(samples[i]);
    const frames: Uint8Array[] = [];
    while (this.pending.length >= this.samplesPerFrame) {
      const chunk = this.pending.splice(0, this.samplesPerFrame);
      const bytes = new Uint8Array(chunk.length * 2);
      const view = new DataView(bytes.buffer);
      chunk.forEach((s, i) => view.setInt16(i * 2, s, true));
      frames.push(bytes);
    }
    return frames;
  }
}

/** Turns streamed PCM bytes back into floats. A trailing odd byte is kept for the next chunk. */
export class PcmDecoder {
  private leftover: number | null = null;

  decode(bytes: Uint8Array): Float32Array {
    let data = bytes;
    if (this.leftover !== null) {
      data = new Uint8Array(bytes.length + 1);
      data[0] = this.leftover;
      data.set(bytes, 1);
      this.leftover = null;
    }
    if (data.length % 2 === 1) {
      this.leftover = data[data.length - 1];
      data = data.subarray(0, data.length - 1);
    }
    const view = new DataView(data.buffer, data.byteOffset, data.byteLength);
    const out = new Float32Array(data.length / 2);
    for (let i = 0; i < out.length; i++) out[i] = view.getInt16(i * 2, true) / 0x8000;
    return out;
  }

  reset(): void {
    this.leftover = null;
  }
}

/** "pcm_16000" -> 16000. Returns null for formats this page can't play (mp3, ulaw, ...). */
export function pcmRate(format: string): number | null {
  const m = /^pcm_(\d{4,6})$/.exec(format);
  return m ? Number(m[1]) : null;
}
