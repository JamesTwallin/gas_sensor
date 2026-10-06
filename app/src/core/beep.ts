// The spike beep tone. Pure, no DOM; the player is services/beeper.ts.
//
// The tone is synthesised here rather than bundled as an asset: a dev build
// fetches assets from Metro over HTTP and the Android player could not load it
// that way ("Source error"), whereas a file the app writes itself plays
// everywhere.

/** A high, hard-edged tone: it has to cut through traffic and wind. */
export const BEEP_HZ = 1200;
/** Beeps closer together than this are dropped: the tone is BEEP_TONE_MS long,
 *  so a spike that lasts sounds as an almost continuous alarm. */
export const BEEP_MIN_GAP_MS = 250;
export const BEEP_TONE_MS = 220;

const SAMPLE_RATE = 44_100;
const FADE_MS = 8;

/**
 * A 16-bit mono WAV of the tone, with short fades so it does not click. Odd
 * harmonics are added (a softened square wave) because a pure sine sounds
 * polite; this sounds like an alarm.
 */
export function beepWavBytes(): Uint8Array {
  const n = Math.round((SAMPLE_RATE * BEEP_TONE_MS) / 1000);
  const fade = Math.round((SAMPLE_RATE * FADE_MS) / 1000);
  const dataBytes = n * 2;
  const buf = new ArrayBuffer(44 + dataBytes);
  const v = new DataView(buf);
  const ascii = (at: number, s: string) => {
    for (let i = 0; i < s.length; i++) v.setUint8(at + i, s.charCodeAt(i));
  };
  ascii(0, 'RIFF');
  v.setUint32(4, 36 + dataBytes, true);
  ascii(8, 'WAVE');
  ascii(12, 'fmt ');
  v.setUint32(16, 16, true); // PCM chunk size
  v.setUint16(20, 1, true); // PCM
  v.setUint16(22, 1, true); // mono
  v.setUint32(24, SAMPLE_RATE, true);
  v.setUint32(28, SAMPLE_RATE * 2, true); // byte rate
  v.setUint16(32, 2, true); // block align
  v.setUint16(34, 16, true); // bits per sample
  ascii(36, 'data');
  v.setUint32(40, dataBytes, true);
  for (let i = 0; i < n; i++) {
    const env = Math.min(1, i / fade, (n - 1 - i) / fade);
    const ph = (2 * Math.PI * BEEP_HZ * i) / SAMPLE_RATE;
    const wave = (Math.sin(ph) + Math.sin(3 * ph) / 3 + Math.sin(5 * ph) / 5) / 1.2;
    const s = Math.max(-1, Math.min(1, wave)) * env * 0.98;
    v.setInt16(44 + i * 2, Math.round(s * 32767), true);
  }
  return new Uint8Array(buf);
}
