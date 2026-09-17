// Simulated board: a timer around core/simulator.ts that speaks the same packet
// bytes and control opcodes as the real firmware.

import { OP_SET_INTERVAL, OP_SET_LED, INTERVAL_MAX_MS, INTERVAL_MIN_MS, parseInfo } from '../core/protocol';
import { SimulatedBoard } from '../core/simulator';
import { toDataView, type DeviceLink, type LinkHandlers } from './device';

export class SimDeviceLink implements DeviceLink {
  readonly kind = 'sim' as const;
  readonly name = 'CH4-SIM0';
  readonly board: SimulatedBoard;
  /** Last colour set with opcode 0x03, for the on-screen "board LED". */
  led: [number, number, number] = [0, 0, 0];
  onLed: (rgb: [number, number, number]) => void = () => {};
  private timer: ReturnType<typeof setInterval> | null = null;
  private dropTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(
    private h: LinkHandlers,
    private onReady: () => void,
  ) {
    this.board = new SimulatedBoard({ seed: (Date.now() & 0xffffffff) >>> 0 });
  }

  async connect(): Promise<void> {
    this.h.onStatus('connecting', this.name);
    await new Promise((r) => setTimeout(r, 300));
    this.open();
  }

  private open(): void {
    this.h.onInfo(parseInfo(this.board.infoJson()));
    this.startTimer();
    this.h.onStatus('connected', this.name);
    this.onReady();
  }

  private startTimer(): void {
    if (this.timer) clearInterval(this.timer);
    this.timer = setInterval(() => this.h.onSample(toDataView(this.board.next())), this.board.intervalMs);
  }

  /** Test hook: drop the link for a few seconds to exercise auto-reconnect. */
  simulateDrop(ms = 4000): void {
    if (!this.timer) return;
    clearInterval(this.timer);
    this.timer = null;
    this.h.onStatus('reconnecting', 'simulated link drop');
    this.dropTimer = setTimeout(() => {
      // The board kept sampling while the link was down.
      for (let t = 0; t < ms; t += this.board.intervalMs) this.board.next();
      this.open();
    }, ms);
  }

  async disconnect(): Promise<void> {
    if (this.timer) clearInterval(this.timer);
    if (this.dropTimer) clearTimeout(this.dropTimer);
    this.timer = null;
    this.h.onStatus('idle');
  }

  async control(bytes: Uint8Array): Promise<void> {
    if (bytes[0] === OP_SET_INTERVAL && bytes.length >= 3) {
      const v = bytes[1] | (bytes[2] << 8);
      if (v >= INTERVAL_MIN_MS && v <= INTERVAL_MAX_MS && v !== this.board.intervalMs) {
        this.board.intervalMs = v;
        if (this.timer) this.startTimer();
      }
    } else if (bytes[0] === OP_SET_LED && bytes.length >= 4) {
      this.led = [bytes[1], bytes[2], bytes[3]];
      this.onLed(this.led);
    }
  }
}
