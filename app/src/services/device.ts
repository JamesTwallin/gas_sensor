// A sensor link: the real BLE board or the simulator, behind one interface.

import type { DeviceInfo } from '../core/protocol';

export type LinkStatus = 'idle' | 'connecting' | 'connected' | 'reconnecting' | 'error';

export interface LinkHandlers {
  onSample(bytes: DataView): void;
  onInfo(info: DeviceInfo): void;
  onStatus(status: LinkStatus, detail?: string): void;
}

export interface DeviceLink {
  readonly kind: 'ble' | 'sim';
  readonly name: string;
  /** Connect to the device this link was created for. */
  connect(): Promise<void>;
  /** User-initiated disconnect: stops auto-reconnect. */
  disconnect(): Promise<void>;
  /** Write to the Control characteristic. Silently ignored when not connected. */
  control(bytes: Uint8Array): Promise<void>;
}

/** A board seen while scanning, offered in the device picker. */
export interface ScannedDevice {
  id: string;
  name: string;
  rssi: number | null;
}

export function toDataView(bytes: Uint8Array): DataView {
  return new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
}
