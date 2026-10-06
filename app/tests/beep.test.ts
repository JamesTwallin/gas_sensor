import { describe, expect, it } from 'vitest';
import { BEEP_TONE_MS, beepWavBytes } from '../src/core/beep';

describe('beepWavBytes', () => {
  it('is a well-formed 16-bit mono PCM WAV of the tone length', () => {
    const b = beepWavBytes();
    const v = new DataView(b.buffer);
    const tag = (at: number) => String.fromCharCode(b[at], b[at + 1], b[at + 2], b[at + 3]);
    expect(tag(0)).toBe('RIFF');
    expect(tag(8)).toBe('WAVE');
    expect(tag(12)).toBe('fmt ');
    expect(tag(36)).toBe('data');
    expect(v.getUint16(20, true)).toBe(1); // PCM
    expect(v.getUint16(22, true)).toBe(1); // mono
    expect(v.getUint16(34, true)).toBe(16);
    const rate = v.getUint32(24, true);
    const dataBytes = v.getUint32(40, true);
    expect(b.length).toBe(44 + dataBytes);
    expect(v.getUint32(4, true)).toBe(b.length - 8);
    expect(dataBytes / 2 / rate).toBeCloseTo(BEEP_TONE_MS / 1000, 3);
    // Starts and ends silent (the fades), loud in the middle.
    expect(v.getInt16(44, true)).toBe(0);
    expect(v.getInt16(b.length - 2, true)).toBe(0);
    let peak = 0;
    for (let i = 44; i < b.length; i += 2) peak = Math.max(peak, Math.abs(v.getInt16(i, true)));
    expect(peak).toBeGreaterThan(20000);
  });
});
