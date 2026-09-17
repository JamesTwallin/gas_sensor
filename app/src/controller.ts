// App controller: the port of the web app's src/main.ts. All signal processing
// lives in src/core (pure, tested); this wires BLE/simulator -> core -> UI state,
// GPS, recording and settings.
//
// It is a plain class rather than React state because samples arrive at 4 Hz and
// drive mutable engines (Processor, ChartBuffer, Recorder). React subscribes with
// useSyncExternalStore and only sees an immutable snapshot, published at most once
// per animation frame.

import { AppState, type AppStateStatus } from 'react-native';
import { ChartBuffer, type ChartPoint } from './core/chartData';
import { formatCsvRow, type GpsFix } from './core/csv';
import { Processor, ledColour, type ProcessorOutput } from './core/processor';
import {
  DEFAULT_INFO,
  encodeIdentify,
  encodeSetInterval,
  encodeSetLed,
  parseSample,
  type DeviceInfo,
  type Sample,
} from './core/protocol';
import { rsOhm, vrlFromTap } from './core/sensor';
import type { AppSettings } from './core/settings';
import { scanForSensors, type ScanHandle } from './services/ble';
import { BleDeviceLink } from './services/bleDevice';
import type { DeviceLink, LinkHandlers, LinkStatus, ScannedDevice } from './services/device';
import { GpsService, type GpsStatus } from './services/gps';
import { setKeepAwake } from './services/keepAwake';
import { Recorder, type SurveyFile } from './services/recorder';
import { saveSettings } from './services/settingsStore';
import { SimDeviceLink } from './services/simDevice';

export const LIVE_SPAN_MS = 60_000;

export type Rgb = [number, number, number];

export interface Toast {
  text: string;
  /** Changes on every toast so the view can restart its timer. */
  id: number;
}

export interface UiState {
  settings: AppSettings;
  info: DeviceInfo;
  linkStatus: LinkStatus;
  linkDetail: string;
  linkName: string | null;
  linkKind: 'ble' | 'sim' | null;
  /** A link object exists (connected, connecting or retrying). */
  linked: boolean;
  lastSample: Sample | null;
  lastOut: ProcessorOutput | null;
  lastRs: { ch4: number | null; lpg: number | null };
  droppedPackets: number;
  badPackets: number;
  gpsStatus: GpsStatus;
  gpsDetail: string;
  gpsFix: GpsFix | null;
  recording: boolean;
  recFileName: string | null;
  recRows: number;
  recStartedAt: number;
  recError: string | null;
  /** Last colour the app pushed to a simulated board, for the on-screen LED. */
  simLed: Rgb | null;
  scanning: boolean;
  scanned: ScannedDevice[];
  scanError: string | null;
  toast: Toast | null;
  /** Bumped whenever chart data changes, so chart views re-pull points. */
  chartTick: number;
}

export class AppController {
  private listeners = new Set<() => void>();
  private state: UiState;
  private processor: Processor;
  private chart: ChartBuffer;
  private recorder: Recorder;
  private gps: GpsService;
  private link: DeviceLink | null = null;
  private scan: ScanHandle | null = null;
  private lastSeq: number | null = null;
  private lastLedKey = '';
  private frame: number | null = null;
  private clock: ReturnType<typeof setInterval> | null = null;
  private appStateSub: { remove(): void } | null = null;
  private toastSeq = 0;
  private disposed = false;

  constructor(settings: AppSettings) {
    this.processor = new Processor(settings);
    this.chart = new ChartBuffer(settings.classWindowMs);
    this.recorder = new Recorder(() => this.syncRecorder());
    this.gps = new GpsService((fix, status, detail) => {
      this.patch({ gpsFix: fix, gpsStatus: status, gpsDetail: detail ?? '' });
    });
    this.state = {
      settings,
      info: DEFAULT_INFO,
      linkStatus: 'idle',
      linkDetail: '',
      linkName: null,
      linkKind: null,
      linked: false,
      lastSample: null,
      lastOut: null,
      lastRs: { ch4: null, lpg: null },
      droppedPackets: 0,
      badPackets: 0,
      gpsStatus: 'off',
      gpsDetail: '',
      gpsFix: null,
      recording: false,
      recFileName: null,
      recRows: 0,
      recStartedAt: 0,
      recError: null,
      simLed: null,
      scanning: false,
      scanned: [],
      scanError: null,
      toast: null,
      chartTick: 0,
    };
  }

  // ------------------------------------------------------------ store plumbing
  subscribe = (fn: () => void): (() => void) => {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  };

  getSnapshot = (): UiState => this.state;

  private patch(next: Partial<UiState>, immediate = true): void {
    this.state = { ...this.state, ...next };
    if (immediate) this.emit();
    else this.scheduleEmit();
  }

  private emit(): void {
    for (const fn of this.listeners) fn();
  }

  /** Coalesce the 4 Hz sample stream into one publish per frame. */
  private scheduleEmit(): void {
    if (this.frame !== null) return;
    this.frame = requestAnimationFrame(() => {
      this.frame = null;
      this.emit();
    });
  }

  start(): void {
    // Recording clock and GPS staleness need a tick even when no samples arrive.
    this.clock = setInterval(() => this.patch({}), 1000);
    this.appStateSub = AppState.addEventListener('change', (s: AppStateStatus) => {
      if (s !== 'active') void this.recorder.flush();
    });
    void this.updateKeepAwake();
  }

  dispose(): void {
    this.disposed = true;
    if (this.clock) clearInterval(this.clock);
    if (this.frame !== null) cancelAnimationFrame(this.frame);
    this.appStateSub?.remove();
    this.scan?.stop();
    void this.link?.disconnect();
    void this.gps.stop();
    void this.recorder.stop();
    void setKeepAwake(false);
  }

  // ------------------------------------------------------------ chart access
  /** Points for the live chart (the last LIVE_SPAN_MS, plus a little lead-in). */
  livePoints(): ChartPoint[] {
    const now = this.chartNow();
    return this.chart.since(now - LIVE_SPAN_MS - 1000);
  }

  overviewPoints(): ChartPoint[] {
    return this.chart.all();
  }

  /** Device ms_since_boot of the newest sample: the right edge of both charts. */
  chartNow(): number {
    return this.chart.last?.t ?? 0;
  }

  // ------------------------------------------------------------ device
  private handlers: LinkHandlers = {
    onSample: (dv) => this.handleSample(dv),
    onInfo: (info) => this.patch({ info }),
    onStatus: (linkStatus, detail) => {
      this.patch({ linkStatus, linkDetail: detail ?? '', linkName: this.link?.name ?? null });
      void this.updateKeepAwake();
    },
  };

  private onLinkReady = (): void => {
    this.lastLedKey = ''; // resend LED state after every (re)connect
    this.lastSeq = null;
    const { settings, info } = this.state;
    if (this.link && Math.round(settings.intervalMs) !== Math.round(info.interval_ms)) {
      void this.link.control(encodeSetInterval(settings.intervalMs));
    }
  };

  /** Connect: the simulator starts straight away, a real board opens the picker. */
  connect(): void {
    if (this.link) return;
    if (this.state.settings.simulate) {
      void this.openLink(new SimDeviceLink(this.handlers, this.onLinkReady));
      return;
    }
    this.startScan();
  }

  startScan(): void {
    if (this.scan) return;
    this.patch({ scanning: true, scanned: [], scanError: null });
    this.scan = scanForSensors(
      (scanned) => this.patch({ scanned }),
      (scanError) => this.patch({ scanError }),
    );
  }

  cancelScan(): void {
    this.scan?.stop();
    this.scan = null;
    this.patch({ scanning: false, scanned: [], scanError: null });
  }

  connectTo(target: ScannedDevice): void {
    this.cancelScan();
    void this.openLink(new BleDeviceLink(target, this.handlers, this.onLinkReady));
  }

  private async openLink(l: DeviceLink): Promise<void> {
    this.processor.reset();
    this.chart.clear();
    this.lastSeq = null;
    if (l instanceof SimDeviceLink) l.onLed = (rgb) => this.patch({ simLed: rgb });
    this.link = l;
    this.patch({
      linked: true,
      linkKind: l.kind,
      linkName: l.name,
      lastOut: null,
      lastSample: null,
      droppedPackets: 0,
      badPackets: 0,
      simLed: l.kind === 'sim' ? [0, 0, 0] : null,
      chartTick: this.state.chartTick + 1,
    });
    void this.gps.start();
    try {
      await l.connect();
    } catch (e) {
      this.link = null;
      const msg = e instanceof Error ? e.message : String(e);
      this.patch({ linked: false, linkKind: null, linkName: null, linkStatus: 'idle' });
      if (!/cancel/i.test(msg)) this.toast(`Connect failed: ${msg}`);
    }
  }

  async disconnect(): Promise<void> {
    const l = this.link;
    this.link = null;
    this.patch({ linked: false, linkKind: null, linkName: null, linkStatus: 'idle', simLed: null });
    if (l) await l.disconnect();
    await this.updateKeepAwake();
  }

  toggleConnection(): void {
    if (this.link) void this.disconnect();
    else this.connect();
  }

  private handleSample(dv: DataView): void {
    let s: Sample;
    try {
      s = parseSample(dv);
    } catch (e) {
      this.patch({ badPackets: this.state.badPackets + 1 }, false);
      console.warn(e);
      return;
    }
    const phoneTimeMs = Date.now();
    const { settings, info } = this.state;
    let dropped = this.state.droppedPackets;
    if (this.lastSeq !== null) {
      const gap = (s.seq - this.lastSeq - 1) & 0xffff;
      if (gap > 0 && gap < 1000) dropped += gap;
    }
    this.lastSeq = s.seq;

    const ch4Mv = vrlFromTap(s.ch4TapMv, info.tap_ratio);
    const lpgMv = vrlFromTap(s.lpgTapMv, info.tap_ratio);
    const rs = {
      ch4: rsOhm(ch4Mv, info.rl_ohm, info.vc_mv),
      lpg: rsOhm(lpgMv, info.rl_ohm, info.vc_mv),
    };
    const out = this.processor.push({
      t: s.msSinceBoot,
      ch4Mv,
      lpgMv,
      button: s.flags.button,
      heatersOff: s.flags.heatersOff,
    });
    if (out.rebooted) {
      this.chart.clear();
      this.toast('Sensor restarted: warming up again');
    }
    if (s.flags.button) this.toast('BOOT pressed: re-zeroing baseline');

    const baselineValid = out.state === 'BASELINING' || out.state === 'RUNNING';
    this.chart.push({
      t: s.msSinceBoot,
      ch4: ch4Mv,
      lpg: lpgMv,
      baseline: baselineValid ? out.ch4.baselineMv : null,
    });

    if (this.recorder.recording) {
      this.recorder.add(
        formatCsvRow({
          millisSinceBoot: s.msSinceBoot,
          state: out.state,
          ch4VoutMv: ch4Mv,
          ch4BaselineMv: out.ch4.baselineMv,
          lpgVoutMv: lpgMv,
          lpgBaselineMv: out.lpg.baselineMv,
          tempC: s.tempC,
          humidityPct: s.humidityPct,
          pressureHpa: s.pressureHpa,
          phoneTimeMs,
          gps: this.gps.latest,
          ch4RsOhm: rs.ch4,
          lpgRsOhm: rs.lpg,
          vbatMv: s.vbatMv,
        }),
      );
    }

    if (settings.driveLed && this.link) {
      const rgb = ledColour(out.state, out.ch4.level);
      const key = rgb.join(',');
      if (key !== this.lastLedKey) {
        this.lastLedKey = key;
        void this.link.control(encodeSetLed(...rgb));
      }
    }

    this.patch(
      {
        lastSample: s,
        lastOut: out,
        lastRs: rs,
        droppedPackets: dropped,
        recRows: this.recorder.rows,
        chartTick: this.state.chartTick + 1,
      },
      false,
    );
  }

  requestRezero(): void {
    this.processor.requestRezero();
    this.toast('Re-zeroing baseline');
  }

  identify(): void {
    if (this.link) void this.link.control(encodeIdentify());
    else this.toast('Not connected');
  }

  // ------------------------------------------------------------ recording
  private syncRecorder(): void {
    this.patch({
      recording: this.recorder.recording,
      recFileName: this.recorder.fileName,
      recRows: this.recorder.rows,
      recStartedAt: this.recorder.startedAt,
      recError: this.recorder.lastError,
    });
  }

  async toggleRecording(): Promise<void> {
    try {
      if (this.recorder.recording) {
        const name = await this.recorder.stop();
        this.toast(`Saved ${name}`);
      } else {
        void this.gps.start();
        const name = await this.recorder.start();
        this.toast(`Recording to ${name}`);
        if (!this.link) this.toast('Recording — connect a sensor to log rows');
      }
    } catch (e) {
      this.toast(`Recording failed: ${e instanceof Error ? e.message : String(e)}`);
    }
    await this.updateKeepAwake();
  }

  listSurveys(): Promise<SurveyFile[]> {
    return Recorder.list();
  }

  async shareSurvey(name: string): Promise<void> {
    if (name === this.recorder.fileName) await this.recorder.flush();
    await Recorder.share(name);
  }

  async deleteSurvey(name: string): Promise<void> {
    await Recorder.remove(name);
  }

  // ------------------------------------------------------------ settings
  async updateSetting<K extends keyof AppSettings>(key: K, value: AppSettings[K]): Promise<void> {
    const prev = this.state.settings;
    if (prev[key] === value) return;
    const settings = { ...prev, [key]: value };
    this.patch({ settings });
    void saveSettings(settings);
    this.processor.updateSettings(settings);
    this.chart.spanMs = settings.classWindowMs;
    if (key === 'intervalMs' && this.link) void this.link.control(encodeSetInterval(settings.intervalMs));
    if (key === 'driveLed') this.lastLedKey = '';
    if (key === 'simulate' && this.link) {
      await this.disconnect();
      this.toast('Device mode changed: tap Connect');
    }
    await this.updateKeepAwake();
  }

  // ------------------------------------------------------------ simulator hooks
  private simLink(): SimDeviceLink | null {
    return this.link instanceof SimDeviceLink ? this.link : null;
  }

  get simulatorAttached(): boolean {
    return this.simLink() !== null;
  }

  simPressButton(): void {
    this.simLink()?.board.pressButton();
  }

  simDropLink(): void {
    this.simLink()?.simulateDrop();
  }

  private simUsb = false;
  private simHeatersOff = false;

  simToggleUsb(): void {
    const l = this.simLink();
    if (!l) return;
    this.simUsb = !this.simUsb;
    l.board.setUsb(this.simUsb);
    this.toast(this.simUsb ? 'USB plugged in' : 'USB unplugged');
  }

  simToggleHeaters(): void {
    const l = this.simLink();
    if (!l) return;
    this.simHeatersOff = !this.simHeatersOff;
    l.board.setHeatersOff(this.simHeatersOff);
    this.toast(this.simHeatersOff ? 'Heaters forced off' : 'Heaters on');
  }

  // ------------------------------------------------------------ misc
  toast(text: string): void {
    if (this.disposed) return;
    this.patch({ toast: { text, id: ++this.toastSeq } });
  }

  dismissToast(id: number): void {
    if (this.state.toast?.id === id) this.patch({ toast: null });
  }

  private async updateKeepAwake(): Promise<void> {
    const { settings } = this.state;
    await setKeepAwake(settings.keepAwake && (!!this.link || this.recorder.recording));
  }
}

export type { ProcessorOutput, Sample };
