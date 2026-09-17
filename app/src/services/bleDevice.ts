// Real board over BLE via react-native-ble-plx.
//
// Auto-reconnect: any disconnect the user did not ask for starts a retry loop
// with capped exponential backoff, re-discovering, re-reading Info and
// re-subscribing each time. Same contract the Capacitor version had.

import type { Device, Subscription } from 'react-native-ble-plx';
import { base64ToBytes, base64ToUtf8, bytesToBase64 } from '../core/base64';
import {
  CONTROL_CHAR_UUID,
  DEFAULT_INFO,
  INFO_CHAR_UUID,
  SAMPLE_CHAR_UUID,
  SERVICE_UUID,
  parseInfo,
} from '../core/protocol';
import { bleManager } from './ble';
import { toDataView, type DeviceLink, type LinkHandlers, type ScannedDevice } from './device';

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export class BleDeviceLink implements DeviceLink {
  readonly kind = 'ble' as const;
  name: string;
  private readonly deviceId: string;
  private device: Device | null = null;
  private wantConnected = false;
  private connected = false;
  private reconnecting = false;
  private monitor: Subscription | null = null;
  private disconnectSub: Subscription | null = null;
  /** Control writes need a response unless the characteristic allows fire-and-forget. */
  private writeWithoutResponse = false;

  constructor(
    target: ScannedDevice,
    private h: LinkHandlers,
    /** Called after every (re)connect, e.g. to push interval and LED state. */
    private onReady: () => void,
  ) {
    this.deviceId = target.id;
    this.name = target.name;
  }

  async connect(): Promise<void> {
    this.wantConnected = true;
    try {
      await this.open();
    } catch (e) {
      // First connection failed: keep trying in the background like a drop.
      void this.scheduleReconnect(message(e));
    }
  }

  private async open(): Promise<void> {
    const m = bleManager();
    this.h.onStatus(this.reconnecting ? 'reconnecting' : 'connecting', this.name);
    const device = await m.connectToDevice(this.deviceId, { timeout: 15000 });
    await device.discoverAllServicesAndCharacteristics();
    this.device = device;
    this.connected = true;
    if (device.name) this.name = device.name;

    this.disconnectSub?.remove();
    this.disconnectSub = m.onDeviceDisconnected(this.deviceId, () => this.handleDisconnect());

    try {
      await this.detectControlWriteMode(device);
      try {
        const ch = await device.readCharacteristicForService(SERVICE_UUID, INFO_CHAR_UUID);
        this.h.onInfo(parseInfo(ch.value ? base64ToUtf8(ch.value) : ''));
      } catch (e) {
        console.warn('Info read failed, using spec defaults', e);
        this.h.onInfo(DEFAULT_INFO);
      }
      this.monitor?.remove();
      this.monitor = device.monitorCharacteristicForService(
        SERVICE_UUID,
        SAMPLE_CHAR_UUID,
        (error, ch) => {
          if (error) {
            // A cancelled monitor is the normal path out of disconnect().
            if (this.wantConnected) console.warn('sample monitor', error.message);
            return;
          }
          if (!ch?.value) return;
          try {
            this.h.onSample(toDataView(base64ToBytes(ch.value)));
          } catch (e) {
            console.warn('bad sample payload', e);
          }
        },
      );
    } catch (e) {
      this.connected = false;
      throw e;
    }
    this.h.onStatus('connected', this.name);
    this.onReady();
  }

  /** The firmware exposes Control as WRITE | WRITE_NR; prefer the cheaper one. */
  private async detectControlWriteMode(device: Device): Promise<void> {
    try {
      const chars = await device.characteristicsForService(SERVICE_UUID);
      const ctrl = chars.find((c) => c.uuid.toLowerCase() === CONTROL_CHAR_UUID.toLowerCase());
      this.writeWithoutResponse = ctrl?.isWritableWithoutResponse ?? false;
    } catch {
      this.writeWithoutResponse = false;
    }
  }

  private handleDisconnect(): void {
    this.connected = false;
    this.monitor?.remove();
    this.monitor = null;
    if (this.wantConnected) void this.scheduleReconnect('link dropped');
    else this.h.onStatus('idle');
  }

  private async scheduleReconnect(reason: string): Promise<void> {
    if (this.reconnecting) return;
    this.reconnecting = true;
    let delay = 1000;
    while (this.wantConnected && !this.connected) {
      this.h.onStatus('reconnecting', `${reason}; retrying in ${Math.round(delay / 1000)} s`);
      await sleep(delay);
      if (!this.wantConnected) break;
      try {
        await this.open();
      } catch (e) {
        reason = message(e);
        this.connected = false;
        try {
          await bleManager().cancelDeviceConnection(this.deviceId);
        } catch {
          /* already gone */
        }
      }
      delay = Math.min(10_000, delay * 2);
    }
    this.reconnecting = false;
  }

  async disconnect(): Promise<void> {
    this.wantConnected = false;
    this.monitor?.remove();
    this.monitor = null;
    this.disconnectSub?.remove();
    this.disconnectSub = null;
    if (this.connected) {
      try {
        await bleManager().cancelDeviceConnection(this.deviceId);
      } catch {
        /* already gone */
      }
    }
    this.connected = false;
    this.device = null;
    this.h.onStatus('idle');
  }

  async control(bytes: Uint8Array): Promise<void> {
    const d = this.device;
    if (!d || !this.connected) return;
    const payload = bytesToBase64(bytes);
    try {
      if (this.writeWithoutResponse) {
        await d.writeCharacteristicWithoutResponseForService(SERVICE_UUID, CONTROL_CHAR_UUID, payload);
      } else {
        await d.writeCharacteristicWithResponseForService(SERVICE_UUID, CONTROL_CHAR_UUID, payload);
      }
    } catch (e) {
      console.warn('Control write failed', e);
    }
  }
}

function message(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}
