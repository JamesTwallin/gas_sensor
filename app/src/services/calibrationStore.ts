// Per-board Ro calibration, keyed by the board's advertised name (CH4-XXXX),
// since Ro belongs to the sensor element and every board has its own.

import AsyncStorage from '@react-native-async-storage/async-storage';
import { NO_CALIBRATION, sanitizeCalibration, type Calibration } from '../core/ppm';

const KEY = 'ch4survey.calibration.v1';

type Store = Record<string, Calibration>;

async function readAll(): Promise<Store> {
  try {
    const raw = await AsyncStorage.getItem(KEY);
    const j = raw ? (JSON.parse(raw) as Record<string, unknown>) : {};
    const out: Store = {};
    for (const [name, v] of Object.entries(j)) out[name] = sanitizeCalibration(v);
    return out;
  } catch {
    return {};
  }
}

export async function loadCalibration(boardName: string): Promise<Calibration> {
  const all = await readAll();
  return all[boardName] ?? { ...NO_CALIBRATION };
}

export async function saveCalibration(boardName: string, cal: Calibration): Promise<void> {
  try {
    const all = await readAll();
    all[boardName] = cal;
    await AsyncStorage.setItem(KEY, JSON.stringify(all));
  } catch {
    /* storage unavailable: the calibration just does not persist */
  }
}
