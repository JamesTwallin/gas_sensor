// Shared BleManager + scanning + Android runtime permissions.
//
// Capacitor's requestDevice() popped a native chooser; react-native-ble-plx has
// no such thing, so the app scans itself and renders its own picker
// (ui/DevicePicker.tsx). Everything here is about *finding* a board; talking to
// one is bleDevice.ts.

import { PermissionsAndroid, Platform } from 'react-native';
import { BleManager, State, type Device } from 'react-native-ble-plx';
import { SERVICE_UUID } from '../core/protocol';
import type { ScannedDevice } from './device';

let manager: BleManager | null = null;

/** One manager for the process: constructing several fights over the adapter. */
export function bleManager(): BleManager {
  if (!manager) manager = new BleManager();
  return manager;
}

/**
 * Android needs the Bluetooth runtime permissions before a scan returns anything.
 * On API 31+ that is SCAN + CONNECT; the manifest declares SCAN with
 * `neverForLocation`, so no location grant is needed just to find the board (the
 * GPS track asks for location separately). API ≤ 30 has no BLUETOOTH_SCAN and
 * scanning is gated on fine location instead.
 */
export async function requestBlePermissions(): Promise<{ granted: boolean; detail?: string }> {
  if (Platform.OS !== 'android') return { granted: true };
  const api = typeof Platform.Version === 'number' ? Platform.Version : parseInt(String(Platform.Version), 10);
  const wanted =
    api >= 31
      ? [PermissionsAndroid.PERMISSIONS.BLUETOOTH_SCAN, PermissionsAndroid.PERMISSIONS.BLUETOOTH_CONNECT]
      : [PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION];
  try {
    const res = await PermissionsAndroid.requestMultiple(wanted);
    const denied = wanted.filter((p) => res[p] !== PermissionsAndroid.RESULTS.GRANTED);
    if (denied.length === 0) return { granted: true };
    return { granted: false, detail: `Bluetooth permission denied (${denied.join(', ')})` };
  } catch (e) {
    return { granted: false, detail: e instanceof Error ? e.message : String(e) };
  }
}

/** Resolve once the adapter reaches a settled state, so scans don't start too early. */
export async function waitForAdapter(timeoutMs = 8000): Promise<State> {
  const m = bleManager();
  const now = await m.state();
  if (now !== State.Unknown && now !== State.Resetting) return now;
  return new Promise<State>((resolve) => {
    const timer = setTimeout(() => {
      sub.remove();
      resolve(State.Unknown);
    }, timeoutMs);
    const sub = m.onStateChange((s) => {
      if (s === State.Unknown || s === State.Resetting) return;
      clearTimeout(timer);
      sub.remove();
      resolve(s);
    }, true);
  });
}

export interface ScanHandle {
  stop(): void;
}

/**
 * Scan for boards advertising the service UUID. The firmware puts the UUID in the
 * advertisement and the `CH4-XXXX` name in the scan response, so both arrive.
 * `onUpdate` gets the full list, strongest signal first, on every change.
 */
export function scanForSensors(
  onUpdate: (devices: ScannedDevice[]) => void,
  onError: (message: string) => void,
): ScanHandle {
  const m = bleManager();
  const found = new Map<string, ScannedDevice>();
  let stopped = false;

  const emit = () => {
    const list = [...found.values()].sort((a, b) => (b.rssi ?? -999) - (a.rssi ?? -999));
    onUpdate(list);
  };

  const handle: ScanHandle = {
    stop() {
      if (stopped) return;
      stopped = true;
      try {
        m.stopDeviceScan();
      } catch {
        /* adapter already gone */
      }
    },
  };

  void (async () => {
    const perm = await requestBlePermissions();
    if (!perm.granted) return onError(perm.detail ?? 'Bluetooth permission denied');
    const state = await waitForAdapter();
    if (stopped) return;
    if (state !== State.PoweredOn) return onError(`Bluetooth is ${String(state).toLowerCase()}`);
    m.startDeviceScan([SERVICE_UUID], { allowDuplicates: false }, (error, device: Device | null) => {
      if (error) return onError(error.message);
      if (!device) return;
      const name = device.name ?? device.localName ?? device.id;
      const prev = found.get(device.id);
      // Keep the best name seen: the scan response may arrive after the advert.
      found.set(device.id, {
        id: device.id,
        name: prev && prev.name !== prev.id ? prev.name : name,
        rssi: device.rssi ?? null,
      });
      emit();
    });
  })();

  return handle;
}
