// Run: node --experimental-transform-types scripts/pcm.check.ts
import assert from "node:assert/strict";
import { Downsampler, Framer, PcmDecoder, floatToInt16, level, pcmRate } from "../src/lib/voice/pcm.ts";
// 48k -> 16k keeps a 440 Hz tone's length ratio and peak
const inRate = 48000, n = 4800;
const tone = Float32Array.from({ length: n }, (_, i) => 0.5 * Math.sin((2 * Math.PI * 440 * i) / inRate));
const d = new Downsampler(inRate, 16000);
const out = d.push(tone);
assert.equal(out.length, 1600);
const peak = Math.max(...out); assert.ok(peak > 0.45 * 32767 && peak < 0.5 * 32767 + 1, String(peak));
// streaming in odd-sized blocks gives the same total length
const d2 = new Downsampler(44100, 16000); let total = 0;
for (let i = 0; i < 50; i++) total += d2.push(new Float32Array(441 + (i % 3))).length;
assert.ok(Math.abs(total - Math.floor(((441 * 50 + 49) / 44100) * 16000)) <= 2, String(total));
assert.equal(new Downsampler(16000, 16000).push(Float32Array.of(0.1, 0.2, 0.3)).length, 3);
assert.throws(() => new Downsampler(0));
// clamping and signs
assert.equal(floatToInt16(2), 32767); assert.equal(floatToInt16(-2), -32768); assert.equal(floatToInt16(0), 0);
// framing: 3200 samples -> two 3200-byte frames, little endian
const f = new Framer(1600); const frames = f.push(Int16Array.from({ length: 3300 }, (_, i) => (i === 0 ? 258 : 0)));
assert.equal(frames.length, 2); assert.equal(frames[0].length, 3200); assert.deepEqual([...frames[0].slice(0, 2)], [2, 1]);
assert.equal(f.push(new Int16Array(1500)).length, 1);
// decoder: odd split chunks reassemble
const dec = new PcmDecoder(); const bytes = Uint8Array.of(0x00, 0x40, 0x00, 0xc0); // 0.5, -0.5
const a = dec.decode(bytes.subarray(0, 3)), b = dec.decode(bytes.subarray(3));
assert.deepEqual([...a], [0.5]); assert.deepEqual([...b], [-0.5]);
dec.decode(Uint8Array.of(1)); dec.reset(); assert.equal(dec.decode(Uint8Array.of(0, 0)).length, 1);
assert.equal(level(new Float32Array(0)), 0); assert.ok(Math.abs(level(Float32Array.of(0.5, -0.5)) - 0.5) < 1e-6);
assert.equal(pcmRate("pcm_16000"), 16000); assert.equal(pcmRate("mp3_44100_128"), null); assert.equal(pcmRate("ulaw_8000"), null);
console.log("pcm checks passed");
