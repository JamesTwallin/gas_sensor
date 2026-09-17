// Phone GPS: one high-accuracy watch; every sample is tagged with the latest fix.

import * as Location from 'expo-location';
import type { GpsFix } from '../core/csv';

export type GpsStatus = 'off' | 'waiting' | 'ok' | 'denied' | 'error';

export class GpsService {
  latest: GpsFix | null = null;
  status: GpsStatus = 'off';
  private sub: Location.LocationSubscription | null = null;
  private starting = false;

  constructor(private onChange: (fix: GpsFix | null, status: GpsStatus, detail?: string) => void) {}

  async start(): Promise<void> {
    if (this.sub || this.starting) return;
    this.starting = true;
    try {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== 'granted') {
        this.set('denied', 'Location permission denied');
        return;
      }
      this.set('waiting');
      this.sub = await Location.watchPositionAsync(
        {
          accuracy: Location.Accuracy.BestForNavigation,
          // Every fix the receiver produces: a survey wants the track, not
          // distance-gated updates.
          timeInterval: 1000,
          distanceInterval: 0,
        },
        (pos) => {
          this.latest = {
            lat: pos.coords.latitude,
            lon: pos.coords.longitude,
            altM: pos.coords.altitude ?? null,
            accuracyM: pos.coords.accuracy ?? null,
            timestamp: pos.timestamp || Date.now(),
          };
          this.set('ok');
        },
      );
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      this.set(/denied|permission/i.test(msg) ? 'denied' : 'error', msg);
    } finally {
      this.starting = false;
    }
  }

  async stop(): Promise<void> {
    this.sub?.remove();
    this.sub = null;
    this.set('off');
  }

  private set(status: GpsStatus, detail?: string): void {
    this.status = status;
    this.onChange(this.latest, status, detail);
  }
}
