// Root component: top bar, banners, the three views and the action dock.
// Everything that thinks lives in src/controller.ts; this is layout, on the
// Restyle spacing scale (src/ui/restyle.ts).

import { useEffect, useMemo, useState, useSyncExternalStore } from 'react';
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
import { SettingsScreen } from './src/ui/SettingsScreen';
import { SurveysScreen } from './src/ui/SurveysScreen';
import { Banner, Btn, Pill, Toast } from './src/ui/components';
import { fmtDuration } from './src/ui/format';
import { Box, ThemeProvider, darkTheme, lightTheme, spacing } from './src/ui/restyle';
import { themeFor, type Severity } from './src/ui/theme';

type ViewName = 'live' | 'surveys' | 'settings';
const VIEWS: ViewName[] = ['live', 'surveys', 'settings'];
const VIEW_LABEL: Record<ViewName, string> = { live: 'Live', surveys: 'Surveys', settings: 'Settings' };

export default function App() {
  // Settings come from AsyncStorage, so the controller cannot exist until they do.
  const [initial, setInitial] = useState<AppSettings | null>(null);
  useEffect(() => {
    void loadSettings().then(setInitial);
  }, []);
  if (!initial) return <Splash />;
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

function Root({ initialSettings }: { initialSettings: AppSettings }) {
  const controller = useMemo(() => new AppController(initialSettings), [initialSettings]);
  useEffect(() => {
    controller.start();
    return () => controller.dispose();
  }, [controller]);

  const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot);
  const [view, setView] = useState<ViewName>('live');
  const light = state.settings.lightTheme;
  const theme = themeFor(light);

  const connected = state.linked && state.linkStatus === 'connected';
  const f = state.lastSample?.flags;
  const banners: [Severity, string][] = [];
  if (state.linked && state.linkStatus === 'reconnecting')
    banners.push(['warning', `Link lost — reconnecting. ${state.linkDetail}`]);
  if (connected && f?.heatersOff)
    banners.push(['critical', 'HEATERS OFF — low-battery cutoff. Gas readings are invalid. Charge the sensor.']);
  if (connected && f && !f.heatersOff && f.adsOk && f.heaterFault)
    banners.push(['critical', 'Heater rail fault (outside 4.8–5.2 V). Readings unreliable.']);
  if (connected && f && !f.adsOk)
    banners.push(['warning', 'ADS1115 not responding: using ESP32 fallback ADC (lower resolution).']);
  if (connected && f && !f.bmeOk)
    banners.push(['warning', 'SHT40 not responding: no temperature / humidity.']);
  if (state.recError) banners.push(['critical', `Recording write error: ${state.recError}`]);
  if (state.recording && state.gpsStatus !== 'ok')
    banners.push([
      'warning',
      `Recording without GPS (${state.gpsStatus}${state.gpsDetail ? ': ' + state.gpsDetail : ''}).`,
    ]);
  if (state.settings.simulate) banners.push(['info', 'Simulator mode: data is not real.']);
  if (state.linked && state.linkKind === 'bridge')
    banners.push(['info', 'USB bridge: readings relayed from the PC over Wi‑Fi. Board controls are unavailable.']);
  if (state.droppedPackets > 0 || state.badPackets > 0)
    banners.push([
      'info',
      `Missed ${state.droppedPackets} packet(s)${state.badPackets ? `, ${state.badPackets} unreadable` : ''}.`,
    ]);

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
    ? `Streaming every ${state.info.interval_ms} ms · ${state.linkKind === 'bridge' ? 'USB bridge' : state.linkKind === 'sim' ? 'simulator' : 'Bluetooth'}`
    : state.linked
      ? state.linkDetail || 'Connecting…'
      : 'Tap Connect to find your sensor';

  const gpsText = (() => {
    const fix = state.gpsFix;
    if (state.gpsStatus === 'ok' && fix) {
      const acc = fix.accuracyM === null ? '?' : Math.round(fix.accuracyM);
      return `GPS ±${acc} m${isFix(fix, Date.now()) ? '' : ' (weak)'}`;
    }
    if (state.gpsStatus === 'waiting') return 'GPS searching…';
    if (state.gpsStatus === 'denied') return 'GPS denied';
    if (state.gpsStatus === 'error') return 'GPS error';
    return 'GPS off';
  })();

  return (
    <ThemeProvider theme={light ? lightTheme : darkTheme}>
      <SafeAreaProvider>
        <SafeAreaView style={{ flex: 1, backgroundColor: theme.bg }} edges={['top', 'bottom']}>
          <StatusBar style={light ? 'dark' : 'light'} />
          <Box flex={1} width="100%" maxWidth={720} alignSelf="center" paddingHorizontal="l">
            {/* One fixed-height row: the pills change text constantly and must not wrap. */}
            <Box flexDirection="row" gap="s" alignItems="center" height={52}>
              <Pill
                theme={theme}
                status={state.linkStatus}
                onPress={() => (state.linked ? undefined : controller.connect())}
                flex={1}
              >
                {linkText}
              </Pill>
              <Pill theme={theme} ghost>
                {state.lastSample && state.linked
                  ? `🔋 ${batteryPercent(state.lastSample.vbatMv)}%` +
                    (state.lastSample.flags.charging ? ' ⚡' : state.lastSample.flags.usbPower ? ' USB' : '')
                  : '🔋 —'}
              </Pill>
              <Pill theme={theme} ghost>
                {gpsText}
              </Pill>
            </Box>

            {/* Status strip: always the same height, so messages coming and going never shift the layout. */}
            <Box height={44} justifyContent="center" paddingBottom="s">
              {state.recording ? (
                <Banner
                  theme={theme}
                  severity="info"
                  tint={theme.critical}
                  text={`● REC ${fmtDuration(Date.now() - state.recStartedAt)} · ${state.recRows} rows${
                    banners.length ? ` · ${banners[0][1]}` : ''
                  }`}
                />
              ) : banners.length > 0 ? (
                <Banner
                  theme={theme}
                  severity={banners[0][0]}
                  text={banners[0][1] + (banners.length > 1 ? `  (+${banners.length - 1})` : '')}
                />
              ) : (
                <Banner theme={theme} severity="info" text={statusLine} />
              )}
            </Box>

            <ScrollView
              style={{ flex: 1 }}
              contentContainerStyle={{ paddingBottom: spacing.l }}
              keyboardShouldPersistTaps="handled"
            >
              {view === 'live' && <LiveScreen state={state} controller={controller} theme={theme} />}
              {view === 'surveys' && <SurveysScreen state={state} controller={controller} theme={theme} />}
              {view === 'settings' && <SettingsScreen state={state} controller={controller} theme={theme} />}
            </ScrollView>

            <Box gap="s" paddingTop="s" paddingBottom="xs" borderTopWidth={1} style={{ borderTopColor: theme.border }}>
              <Box flexDirection="row" gap="s">
                <Btn
                  theme={theme}
                  big
                  title={state.linked ? 'Disconnect' : 'Connect'}
                  onPress={() => controller.toggleConnection()}
                  style={{ flex: 1 }}
                />
                <Btn
                  theme={theme}
                  big
                  title="Re-zero"
                  disabled={!state.linked || state.lastOut?.state === 'HEATER_OFF'}
                  onPress={() => controller.requestRezero()}
                  style={{ flex: 1 }}
                />
                <Btn
                  theme={theme}
                  big
                  title={state.recording ? '■ Stop' : '● Record'}
                  variant={state.recording ? 'recording' : 'record'}
                  onPress={() => void controller.toggleRecording()}
                  style={{ flex: 1.25 }}
                />
              </Box>
              <Box flexDirection="row" gap="s">
                {VIEWS.map((v) => (
                  <Btn
                    key={v}
                    theme={theme}
                    title={VIEW_LABEL[v]}
                    variant={view === v ? 'primary' : 'default'}
                    onPress={() => setView(v)}
                    style={{ flex: 1 }}
                  />
                ))}
              </Box>
            </Box>
          </Box>

          <DevicePicker state={state} controller={controller} theme={theme} />
          {state.toast && (
            <Toast
              theme={theme}
              text={state.toast.text}
              id={state.toast.id}
              onDone={(id) => controller.dismissToast(id)}
            />
          )}
        </SafeAreaView>
      </SafeAreaProvider>
    </ThemeProvider>
  );
}

export type { ViewName };
