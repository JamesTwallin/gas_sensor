// Settings persistence. AsyncStorage is async, so the app shows nothing until the
// first load resolves (App.tsx) -- the whole controller depends on the settings.

import AsyncStorage from '@react-native-async-storage/async-storage';
import { DEFAULT_SETTINGS, sanitizeSettings, type AppSettings } from '../core/settings';

const KEY = 'ch4survey.settings.v1';

export async function loadSettings(): Promise<AppSettings> {
  try {
    const raw = await AsyncStorage.getItem(KEY);
    return raw ? sanitizeSettings(JSON.parse(raw)) : { ...DEFAULT_SETTINGS };
  } catch {
    return { ...DEFAULT_SETTINGS };
  }
}

export async function saveSettings(s: AppSettings): Promise<void> {
  try {
    await AsyncStorage.setItem(KEY, JSON.stringify(s));
  } catch {
    /* storage full / unavailable: settings just don't persist */
  }
}
