// App controller. All signal processing lives in src/core (pure, tested); this
// wires BLE/simulator -> core -> UI state, GPS, recording and settings.
//
// It is a plain class rather than React state because samples arrive at 4 Hz and
// drive mutable engines (Processor, ChartBuffer, Recorder). React subscribes with
// useSyncExternalStore and only sees an immutable snapshot, published at most once
// per animation frame.

import { AppState, NativeModules, type AppStateStatus } from 'react-native';
import { bridgeUrl } from './core/bridge';
import { ChartBuffer, type ChartPoint } from './core/chartData';
import { formatCsvRow, type GpsFix } from './core/csv';
import {
  NO_CALIBRATION,
  TGS2610,
  TGS2611,
  estimatePpm,
  roFor,
  roFromKnownPpm,
  type Calibration,
  type ChannelCalibration,
} from './core/ppm';
import { Processor, ledColour, type ProcessorOutput } from './core/processor';
import { NO_SPIKE, SPIKE_BURST_GAP_MS, SPIKE_HOLD_MS, SpikeDetector, type SpikeResult } from './core/spike';
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
import { bleAvailable, scanForSensors, type ScanHandle } from './services/ble';
import { BleDeviceLink } from './services/bleDevice';
import { BridgeDeviceLink } from './services/bridgeDevice';
import { loadCalibration, saveCalibration } from './services/calibrationStore';
import type { DeviceLink, LinkHandlers, LinkStatus, ScannedDevice } from './services/device';
import { GpsService, type GpsStatus } from './services/gps';
import { beep, disposeBeeper, prepareBeeper } from './services/beeper';
import { setKeepAwake } from './services/keepAwake';
import { Recorder, type SurveyFile } from './services/recorder';
import { saveSettings } from './services/settingsStore';
import { SimDeviceLink } from './services/simDevice';

export const LIVE_SPAN_MS = 60_000;
/** History kept for the peak-slope overview strip. */
export const OVERVIEW_SPAN_MS = 10 * 60_000;

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
  linkKind: 'ble' | 'sim' | 'bridge' | null;
  /** A link object exists (connected, connecting or retrying). */
  linked: boolean;
  lastSample: Sample | null;
  lastOut: ProcessorOutput | null;
  lastRs: { ch4: number | null; lpg: number | null };
  /** Datasheet-curve concentration estimates (core/ppm.ts). */
  lastPpm: { ch4: number | null; lpg: number | null };
  /** Ro calibration for the connected board (datasheet-typical Ro where null). */
  calibration: Calibration;
  /** Spike detector (core/spike.ts): latest per-channel result and the last burst. */
  spikes: {
    ch4: SpikeResult;
    lpg: SpikeResult;
    /** A sample was flagged within the last SPIKE_HOLD_MS: what the card, the LED and presentation mode show. */
    active: { ch4: boolean; lpg: boolean };
    /** Phone epoch ms of the last new burst, null if none yet. */
    lastAt: number | null;
    /** e.g. "CH4 +812 mV/s". */
    lastText: string | null;
    /** Bursts since connecting. */
    count: number;
  };
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

const IDLE_SPIKES: UiState['spikes'] = {
  ch4: NO_SPIKE,
  lpg: NO_SPIKE,
  active: { ch4: false, lpg: false },
  lastAt: null,
  lastText: null,
  count: 0,
};

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
  private spike = { ch4: new SpikeDetector(), lpg: new SpikeDetector() };
  /** Device ms of the last sample flagged per channel, for burst grouping. */
  private lastSpikeT = { ch4: -Infinity, lpg: -Infinity };
  private frame: number | null = null;
  private clock: ReturnType<typeof setInterval> | null = null;
  private appStateSub: { remove(): void } | null = null;
  private toastSeq = 0;
  private disposed = false;

  constructor(settings: AppSettings) {
    this.processor = new Processor(settings);
    this.spike = { ch4: new SpikeDetector(settings), lpg: new SpikeDetector(settings) };
    this.chart = new ChartBuffer(OVERVIEW_SPAN_MS);
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
      lastPpm: { ch4: null, lpg: null },
      calibration: { ...NO_CALIBRATION },
      spikes: IDLE_SPIKES,
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
    if (this.state.settings.beep) void prepareBeeper();
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
    disposeBeeper();
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
    const name = this.link?.name;
    if (name) {
      void loadCalibration(name).then((calibration) => {
        if (this.link?.name === name) this.patch({ calibration });
      });
    }
    const { settings, info } = this.state;
    if (this.link && Math.round(settings.intervalMs) !== Math.round(info.interval_ms)) {
      void this.link.control(encodeSetInterval(settings.intervalMs));
    }
  };

  /**
   * Connect: the simulator starts straight away, the USB bridge connects to
   * the PC, a real board over BLE opens the picker. Without the BLE native
   * module (Expo Go) the bridge is the only real link, so it is used even when
   * the setting is off.
   */
  connect(): void {
    if (this.link) return;
    const { settings } = this.state;
    if (settings.simulate) {
      void this.openLink(new SimDeviceLink(this.handlers, this.onLinkReady));
      return;
    }
    if (settings.usbBridge || !bleAvailable()) {
      const scriptUrl = (NativeModules.SourceCode as { scriptURL?: string } | undefined)?.scriptURL;
      const url = bridgeUrl(settings.bridgeHost, scriptUrl);
      if (!url) {
        this.toast('Set the bridge PC address in Settings');
        return;
      }
      if (!settings.usbBridge) this.toast('No Bluetooth in Expo Go: using the USB bridge');
      void this.openLink(new BridgeDeviceLink(url, this.handlers, this.onLinkReady));
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
    this.spike.ch4.reset();
    this.spike.lpg.reset();
    this.lastSpikeT = { ch4: -Infinity, lpg: -Infinity };
    this.patch({ spikes: IDLE_SPIKES }, false);
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
    const cal = this.state.calibration;
    // With compensation off, null T/RH makes the curves use their reference conditions.
    const envT = settings.envCompensate ? s.tempC : null;
    const envRh = settings.envCompensate ? s.humidityPct : null;
    const ppm = {
      ch4: estimatePpm(rs.ch4, roFor(cal.ch4, TGS2611), envT, envRh, TGS2611),
      lpg: estimatePpm(rs.lpg, roFor(cal.lpg, TGS2610), envT, envRh, TGS2610),
    };
    const out = this.processor.push({
      t: s.msSinceBoot,
      ch4Mv,
      lpgMv,
      heatersOff: s.flags.heatersOff,
    });
    // A board restart resets the processor to WARMUP, which the state card
    // already shows; no toast, it fired on every bench reflash and power cycle.
    if (out.rebooted) this.chart.clear();

    // The slope is computed whenever the heaters are on, so the trace is never
    // blank, but a sample only counts as a spike once the warm-up is over: a
    // cold element ramps steeply for minutes and would flag the whole time.
    const heatersOn = out.state !== 'HEATER_OFF';
    const running = out.state === 'RUNNING';
    if (!heatersOn || out.rebooted) {
      this.spike.ch4.reset();
      this.spike.lpg.reset();
      // Device time restarted (or is about to): old spike times no longer compare.
      this.lastSpikeT = { ch4: -Infinity, lpg: -Infinity };
    }
    const detect = (d: SpikeDetector, mv: number): SpikeResult => {
      const r = d.push(s.msSinceBoot, mv);
      return running ? r : { ...r, spike: false };
    };
    const sp = heatersOn
      ? { ch4: detect(this.spike.ch4, ch4Mv), lpg: detect(this.spike.lpg, lpgMv) }
      : { ch4: NO_SPIKE, lpg: NO_SPIKE };
    const bursts: string[] = [];
    const active = { ch4: false, lpg: false };
    let flagged = false;
    for (const ch of ['ch4', 'lpg'] as const) {
      if (sp[ch].spike) {
        if (s.msSinceBoot - this.lastSpikeT[ch] > SPIKE_BURST_GAP_MS) {
          bursts.push(`${ch.toUpperCase()} +${Math.round(sp[ch].slopeMvPerS ?? 0)} mV/s`);
        }
        this.lastSpikeT[ch] = s.msSinceBoot;
        flagged = true;
      }
      active[ch] = s.msSinceBoot - this.lastSpikeT[ch] <= SPIKE_HOLD_MS;
    }
    // Every flagged sample beeps (rate-limited in the beeper), so a plume is
    // heard as a run of tones.
    if (flagged && settings.beep) beep(phoneTimeMs);
    let spikes = { ...this.state.spikes, ch4: sp.ch4, lpg: sp.lpg, active };
    if (bursts.length) {
      // No toast: the red card, the beep and the LED already say it.
      spikes = { ...spikes, lastAt: phoneTimeMs, lastText: bursts.join(', '), count: spikes.count + bursts.length };
      // Three white blinks on the board (opcode 0x02) so a plume is visible without the phone.
      if (settings.driveLed && this.link) void this.link.control(encodeIdentify());
    }
    const spikeText = sp.ch4.spike && sp.lpg.spike ? 'CH4+LPG' : sp.ch4.spike ? 'CH4' : sp.lpg.spike ? 'LPG' : '';

    this.chart.push({
      t: s.msSinceBoot,
      ch4: ch4Mv,
      lpg: lpgMv,
      ch4Slope: sp.ch4.slopeMvPerS,
      lpgSlope: sp.lpg.slopeMvPerS,
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
          ch4PpmEst: ppm.ch4,
          lpgPpmEst: ppm.lpg,
          ch4SlopeMvPerS: sp.ch4.slopeMvPerS,
          lpgSlopeMvPerS: sp.lpg.slopeMvPerS,
          spike: spikeText,
        }),
      );
    }

    if (settings.driveLed && this.link) {
      const rgb = ledColour(out.state, active.ch4);
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
        lastPpm: ppm,
        spikes,
        droppedPackets: dropped,
        recRows: this.recorder.rows,
        chartTick: this.state.chartTick + 1,
      },
      false,
    );
  }

  identify(): void {
    if (this.link) void this.link.control(encodeIdentify());
    else this.toast('Not connected');
  }

  // ------------------------------------------------------------ calibration
  /**
   * Take Ro for one channel from the current reading, given the concentration
   * the sensor is sitting in right now. Stored per board name.
   */
  calibrate(channel: 'ch4' | 'lpg', knownPpm: number): void {
    const name = this.link?.name;
    const s = this.state.lastSample;
    const rs = this.state.lastRs[channel];
    if (!name || !s || rs === null) {
      this.toast('Connect and wait for a reading first');
      return;
    }
    if (!(knownPpm > 0)) {
      this.toast('Enter the concentration the sensor is in');
      return;
    }
    const curve = channel === 'ch4' ? TGS2611 : TGS2610;
    const comp = this.state.settings.envCompensate;
    const rec: ChannelCalibration = {
      roOhm: roFromKnownPpm(rs, knownPpm, comp ? s.tempC : null, comp ? s.humidityPct : null, curve),
      ppm: knownPpm,
      at: Date.now(),
      tempC: s.tempC,
      rh: s.humidityPct,
    };
    const calibration = { ...this.state.calibration, [channel]: rec };
    this.patch({ calibration });
    void saveCalibration(name, calibration);
    this.toast(`${curve.gas} Ro set to ${Math.round(rec.roOhm)} Ω`);
  }

  resetCalibration(): void {
    const name = this.link?.name;
    const calibration = { ...NO_CALIBRATION };
    this.patch({ calibration });
    if (name) void saveCalibration(name, calibration);
    this.toast('Back to datasheet-typical Ro');
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
    this.spike.ch4.updateSettings(settings);
    this.spike.lpg.updateSettings(settings);
    if (key === 'intervalMs' && this.link) void this.link.control(encodeSetInterval(settings.intervalMs));
    if (key === 'driveLed') this.lastLedKey = '';
    if ((key === 'simulate' || key === 'usbBridge' || key === 'bridgeHost') && this.link) {
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
