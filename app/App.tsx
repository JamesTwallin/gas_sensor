// Root component: header, status strip, the three views and the action dock.
// Everything that thinks lives in src/controller.ts; this is layout, on the
// Restyle spacing scale (src/ui/restyle.ts), set in Inter.

import {
  Inter_400Regular,
  Inter_500Medium,
  Inter_600SemiBold,
  Inter_700Bold,
  Inter_800ExtraBold,
  useFonts,
} from '@expo-google-fonts/inter';
import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import { ActivityIndicator, ScrollView } from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { AppController } from './src/controller';
import { isFix } from './src/core/csv';
import type { AppSettings } from './src/core/settings';
import { batteryPercent } from './src/core/simulator';
import { loadSettings } from './src/services/settingsStore';
import { DevicePicker } from './src/ui/DevicePicker';
import { LiveScreen } from './src/ui/LiveScreen';
import { PresentScreen } from './src/ui/PresentScreen';
import { SettingsScreen } from './src/ui/SettingsScreen';
import { SurveysScreen } from './src/ui/SurveysScreen';
import { Btn, LinkChip, MetaChip, SegmentedTabs, StatusStrip, Toast, type IconName } from './src/ui/components';
import { fmtDuration } from './src/ui/format';
import { Box, ThemeProvider, darkTheme, lightTheme, spacing } from './src/ui/restyle';
import { themeFor, type Severity } from './src/ui/theme';

type ViewName = 'live' | 'surveys' | 'settings';
const TABS: { key: ViewName; label: string; icon: IconName }[] = [
  { key: 'live', label: 'Live', icon: 'pulse' },
  { key: 'surveys', label: 'Surveys', icon: 'map-marker-path' },
  { key: 'settings', label: 'Settings', icon: 'tune-variant' },
];

export default function App() {
  // Settings come from AsyncStorage, so the controller cannot exist until they
  // do; the fonts are bundled but still load asynchronously on first launch.
  const [initial, setInitial] = useState<AppSettings | null>(null);
  const [fontsReady] = useFonts({ Inter_400Regular, Inter_500Medium, Inter_600SemiBold, Inter_700Bold, Inter_800ExtraBold });
  useEffect(() => {
    void loadSettings().then(setInitial);
  }, []);
  if (!initial || !fontsReady) return <Splash />;
  return <Root initialSettings={initial} />;
}

function Splash() {
  const theme = themeFor(false);
  return (
    <ThemeProvider theme={darkTheme}>
      <Box flex={1} alignItems="center" justifyContent="center" style={{ backgroundColor: theme.bg }}>
        <ActivityIndicator size="large" color={theme.text} />
      </Box>
    </ThemeProvider>
  );
}

function batteryIcon(percent: number, charging: boolean): IconName {
  if (charging) return 'battery-charging';
  if (percent >= 95) return 'battery';
  if (percent < 10) return 'battery-outline';
  return `battery-${Math.round(percent / 10) * 10}` as IconName;
}

function Root({ initialSettings }: { initialSettings: AppSettings }) {
  const controller = useMemo(() => new AppController(initialSettings), [initialSettings]);
  useEffect(() => {
    controller.start();
    return () => controller.dispose();
  }, [controller]);

  const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot);
  const [view, setView] = useState<ViewName>('live');
  // Flash the scroll bar on every tab switch so it is obvious the page goes on
  // below the fold (the Surveys list sits under the map).
  const scroller = useRef<ScrollView>(null);
  useEffect(() => {
    const t = setTimeout(() => scroller.current?.flashScrollIndicators(), 300);
    return () => clearTimeout(t);
  }, [view]);
  // Presentation mode (ui/PresentScreen.tsx) replaces everything below the status bar.
  const [presenting, setPresenting] = useState(false);
  const stopPresenting = useCallback(() => setPresenting(false), []);
  // Toasts stay out of the video: dropped as they arrive, so none is left to pop up on exit.
  const toastId = state.toast?.id;
  useEffect(() => {
    if (presenting && toastId !== undefined) controller.dismissToast(toastId);
  }, [presenting, toastId, controller]);
  const light = state.settings.lightTheme;
  const theme = themeFor(light);

  const connected = state.linked && state.linkStatus === 'connected';
  const f = state.lastSample?.flags;
  const banners: [Severity, string][] = [];
  if (connected && state.spikes.lastAt !== null && Date.now() - state.spikes.lastAt < 30_000)
    banners.push(['critical', `Spike detected: ${state.spikes.lastText}`]);
  if (state.linked && state.linkStatus === 'reconnecting')
    banners.push(['warning', `Link lost, reconnecting · ${state.linkDetail}`]);
  if (connected && f?.heatersOff)
    banners.push(['critical', 'Heaters off: low battery. Gas readings are invalid.']);
  if (connected && f && !f.heatersOff && f.adsOk && f.heaterFault)
    banners.push(['critical', 'Heater rail fault (outside 4.8–5.2 V). Readings unreliable.']);
  if (connected && f && !f.adsOk)
    banners.push(['warning', 'ADS1115 not responding: using ESP32 fallback ADC.']);
  if (connected && f && !f.bmeOk) banners.push(['warning', 'SHT40 not responding: no temperature / humidity.']);
  if (state.recError) banners.push(['critical', `Recording write error: ${state.recError}`]);
  if (state.recording && state.gpsStatus !== 'ok')
    banners.push(['warning', `Recording without GPS (${state.gpsStatus}${state.gpsDetail ? ': ' + state.gpsDetail : ''}).`]);
  if (state.settings.simulate) banners.push(['info', 'Simulator: data is not real.']);
  if (state.linked && state.linkKind === 'bridge')
    banners.push(['info', 'USB bridge via PC: board controls unavailable.']);
  if (state.droppedPackets > 0 || state.badPackets > 0)
    banners.push(['info', `Missed ${state.droppedPackets} packet(s)${state.badPackets ? `, ${state.badPackets} unreadable` : ''}.`]);

  const linkText =
    state.linkStatus === 'connected'
      ? (state.linkName ?? 'Connected')
      : state.linkStatus === 'connecting'
        ? 'Connecting…'
        : state.linkStatus === 'reconnecting'
          ? 'Reconnecting…'
          : 'Not connected';

  // Quiet baseline for the status strip when nothing needs saying.
  const statusLine = connected
    ? `Streaming every ${state.info.interval_ms} ms over ${
        state.linkKind === 'bridge' ? 'the USB bridge' : state.linkKind === 'sim' ? 'the simulator' : 'Bluetooth'
      }`
    : state.linked
      ? state.linkDetail || 'Connecting…'
      : 'Tap Connect to find your sensor';

  const battery = (() => {
    const s = state.lastSample;
    if (!s || !state.linked) return { icon: 'battery-unknown' as IconName, text: '—' };
    // On USB the cell voltage is the charger's, not a charge level, and with no
    // cell fitted the input floats anywhere: just say USB. Battery % is for
    // battery operation.
    if (s.flags.usbPower) return { icon: (s.flags.charging ? 'battery-charging' : 'usb-port') as IconName, text: 'USB' };
    if (s.vbatMv < 3000) return { icon: 'battery-unknown' as IconName, text: '—' };
    const p = batteryPercent(s.vbatMv);
    return { icon: batteryIcon(p, s.flags.charging), text: `${p}%` };
  })();

  const gps = (() => {
    const fix = state.gpsFix;
    if (state.gpsStatus === 'ok' && fix) {
      const acc = fix.accuracyM === null ? '?' : Math.round(fix.accuracyM);
      const weak = !isFix(fix, Date.now());
      return { icon: (weak ? 'crosshairs' : 'crosshairs-gps') as IconName, text: `±${acc} m`, tint: weak ? theme.warning : undefined };
    }
    if (state.gpsStatus === 'waiting') return { icon: 'crosshairs-question' as IconName, text: 'searching', tint: undefined };
    if (state.gpsStatus === 'denied') return { icon: 'crosshairs-off' as IconName, text: 'denied', tint: theme.warning };
    if (state.gpsStatus === 'error') return { icon: 'crosshairs-off' as IconName, text: 'error', tint: theme.warning };
    return { icon: 'crosshairs-off' as IconName, text: 'off', tint: undefined };
  })();

  return (
    <ThemeProvider theme={light ? lightTheme : darkTheme}>
      <SafeAreaProvider>
        <SafeAreaView style={{ flex: 1, backgroundColor: theme.bg }} edges={['top', 'bottom']}>
          <StatusBar style={light ? 'dark' : 'light'} hidden={presenting} />
          {presenting ? (
            <PresentScreen state={state} controller={controller} theme={theme} onExit={stopPresenting} />
          ) : (
          <Box flex={1} width="100%" maxWidth={720} alignSelf="center" paddingHorizontal="l">
            {/* Header: one fixed-height row. The link chip ellipsises; the chips never wrap. */}
            <Box flexDirection="row" alignItems="center" gap="xs" height={56}>
              <LinkChip
                theme={theme}
                status={state.linkStatus}
                label={linkText}
                onPress={() => (state.linked ? undefined : controller.connect())}
              />
              <MetaChip theme={theme} icon={battery.icon} text={battery.text} />
              <MetaChip theme={theme} icon={gps.icon} text={gps.text} tint={gps.tint} />
            </Box>

            {/* Status strip: always the same height, so messages coming and going never shift the layout. */}
            <Box height={40} justifyContent="center">
              {state.recording ? (
                <StatusStrip
                  theme={theme}
                  severity="info"
                  icon="record-circle"
                  tint={theme.critical}
                  text={`REC ${fmtDuration(Date.now() - state.recStartedAt)} · ${state.recRows} rows${
                    banners.length ? ` · ${banners[0][1]}` : ''
                  }`}
                />
              ) : banners.length > 0 ? (
                <StatusStrip
                  theme={theme}
                  severity={banners[0][0]}
                  text={banners[0][1] + (banners.length > 1 ? `  (+${banners.length - 1})` : '')}
                />
              ) : (
                <StatusStrip theme={theme} severity="quiet" text={statusLine} />
              )}
            </Box>

            <ScrollView
              ref={scroller}
              style={{ flex: 1 }}
              contentContainerStyle={{ paddingTop: spacing.xs, paddingBottom: spacing.l }}
              keyboardShouldPersistTaps="handled"
            >
              {view === 'live' && <LiveScreen state={state} controller={controller} theme={theme} />}
              {view === 'surveys' && <SurveysScreen state={state} controller={controller} theme={theme} />}
              {view === 'settings' && <SettingsScreen state={state} controller={controller} theme={theme} />}
            </ScrollView>

            <Box gap="s" paddingTop="s" paddingBottom="xs">
              <Box flexDirection="row" gap="s">
                <Btn
                  theme={theme}
                  big
                  title={state.linked ? 'Disconnect' : 'Connect'}
                  icon={state.linked ? 'bluetooth-off' : 'bluetooth'}
                  variant={state.linked ? 'default' : 'accent'}
                  onPress={() => controller.toggleConnection()}
                  style={{ flex: 1.2 }}
                />
                <Btn theme={theme} big title="Present" onPress={() => setPresenting(true)} style={{ flex: 1 }} />
                <Btn
                  theme={theme}
                  big
                  title={state.recording ? 'Stop' : 'Record'}
                  icon={state.recording ? 'stop' : 'record'}
                  variant={state.recording ? 'recording' : 'record'}
                  onPress={() => void controller.toggleRecording()}
                  style={{ flex: 1 }}
                />
              </Box>
              <SegmentedTabs theme={theme} items={TABS} value={view} onChange={setView} />
            </Box>
          </Box>
          )}

          <DevicePicker state={state} controller={controller} theme={theme} />
          {state.toast && !presenting && (
            <Toast theme={theme} text={state.toast.text} id={state.toast.id} onDone={(id) => controller.dismissToast(id)} />
          )}
        </SafeAreaView>
      </SafeAreaProvider>
    </ThemeProvider>
  );
}

export type { ViewName };
