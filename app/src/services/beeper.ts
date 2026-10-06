// Spike beeper: a short tone on every flagged sample, so a plume can be heard
// (and heard on a video) without looking at the screen.
//
// The tone (core/beep.ts) is written to the cache directory once and played
// from there.

import { createAudioPlayer, setAudioModeAsync, type AudioPlayer } from 'expo-audio';
import { File, Paths } from 'expo-file-system';
import { BEEP_HZ, BEEP_MIN_GAP_MS, BEEP_TONE_MS, beepWavBytes } from '../core/beep';

/** Named by its parameters, so a changed tone is written afresh. */
const TONE_FILE = `beep-${BEEP_HZ}hz-${BEEP_TONE_MS}ms-v2.wav`;

let player: AudioPlayer | null = null;
let ready: Promise<void> | null = null;
let lastBeepAt = -Infinity;

/** Create the player (once); call early so the first beep is not spent loading. */
export function prepareBeeper(): Promise<void> {
  if (!ready) {
    ready = (async () => {
      const file = new File(Paths.cache, TONE_FILE);
      const bytes = beepWavBytes();
      if (!file.exists || file.size !== bytes.length) file.write(bytes);
      // Audible with the iPhone mute switch on: this is an instrument alert, not media.
      await setAudioModeAsync({ playsInSilentMode: true, interruptionMode: 'mixWithOthers' });
      player = createAudioPlayer({ uri: file.uri });
    })().catch((e) => {
      console.warn('beeper', e);
      player = null;
    });
  }
  return ready;
}

/** Play the tone, unless one played within BEEP_MIN_GAP_MS. */
export function beep(nowMs = Date.now()): void {
  if (nowMs - lastBeepAt < BEEP_MIN_GAP_MS) return;
  lastBeepAt = nowMs;
  void prepareBeeper().then(async () => {
    if (!player) return;
    try {
      await player.seekTo(0);
      player.play();
    } catch (e) {
      console.warn('beeper', e);
    }
  });
}

export function disposeBeeper(): void {
  player?.remove();
  player = null;
  ready = null;
}
