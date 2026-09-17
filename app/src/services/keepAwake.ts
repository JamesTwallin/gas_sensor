// Screen wake lock while connected or recording (a survey is watched, not read).

import { activateKeepAwakeAsync, deactivateKeepAwake } from 'expo-keep-awake';

const TAG = 'ch4-survey';
let held = false;

/** Hold or release the wake lock; failures (web, unsupported) are ignored. */
export async function setKeepAwake(on: boolean): Promise<void> {
  if (on === held) return;
  try {
    if (on) await activateKeepAwakeAsync(TAG);
    else await deactivateKeepAwake(TAG);
    held = on;
  } catch (e) {
    console.warn('keep-awake', e);
  }
}
