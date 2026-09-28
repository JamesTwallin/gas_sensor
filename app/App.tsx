// Root component: top bar, banners, the three views and the action dock.
// Everything that thinks lives in src/app/controller.ts; this is layout.

import { useEffect, useMemo, useState, useSyncExternalStore } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, View } from 'react-native';
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
import { TAP, themeFor, type Severity } from './src/ui/theme';

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
    <View style={[styles.splash, { backgroundColor: theme.bg }]}>
      <ActivityIndicator size="large" color={theme.text} />
    </View>
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
  const theme = themeFor(state.settings.lightTheme);

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
    banners.push(['warning', 'BME280 not responding: no temperature / humidity / pressure.']);
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
    <SafeAreaProvider>
      <SafeAreaView style={[styles.root, { backgroundColor: theme.bg }]} edges={['top', 'bottom']}>
        <StatusBar style={state.settings.lightTheme ? 'dark' : 'light'} />
        <View style={styles.inner}>
          <View style={styles.topbar}>
            <Pill
              theme={theme}
              status={state.linkStatus}
              onPress={() => (state.linked ? undefined : controller.connect())}
            >
              {linkText}
            </Pill>
            {state.lastSample && state.linked && (
              <Pill theme={theme} ghost>
                {`🔋 ${batteryPercent(state.lastSample.vbatMv)}%` +
                  (state.lastSample.flags.charging
                    ? ' ⚡charging'
                    : state.lastSample.flags.usbPower
                      ? ' USB'
                      : '')}
              </Pill>
            )}
            <Pill theme={theme} ghost>
              {gpsText}
            </Pill>
            {state.recording && (
              <Pill theme={theme} ghost tint={theme.critical}>
                {`● REC ${fmtDuration(Date.now() - state.recStartedAt)} · ${state.recRows} rows`}
              </Pill>
            )}
          </View>

          {banners.map(([severity, text]) => (
            <Banner key={text} theme={theme} severity={severity} text={text} />
          ))}

          <ScrollView
            style={styles.scroll}
            contentContainerStyle={styles.scrollContent}
            keyboardShouldPersistTaps="handled"
          >
            {view === 'live' && <LiveScreen state={state} controller={controller} theme={theme} />}
            {view === 'surveys' && <SurveysScreen state={state} controller={controller} theme={theme} />}
            {view === 'settings' && <SettingsScreen state={state} controller={controller} theme={theme} />}
          </ScrollView>

          <View style={styles.dock}>
            <View style={styles.actions}>
              <Btn
                theme={theme}
                big
                title={state.linked ? 'Disconnect' : 'Connect'}
                onPress={() => controller.toggleConnection()}
                style={styles.action}
              />
              <Btn
                theme={theme}
                big
                title="Re-zero"
                disabled={!state.linked || state.lastOut?.state === 'HEATER_OFF'}
                onPress={() => controller.requestRezero()}
                style={styles.action}
              />
              <Btn
                theme={theme}
                big
                title={state.recording ? '■ Stop' : '● Record'}
                variant={state.recording ? 'recording' : 'record'}
                onPress={() => void controller.toggleRecording()}
                style={styles.actionWide}
              />
            </View>
            <View style={styles.tabs}>
              {VIEWS.map((v) => (
                <Btn
                  key={v}
                  theme={theme}
                  title={VIEW_LABEL[v]}
                  variant={view === v ? 'primary' : 'default'}
                  onPress={() => setView(v)}
                  style={styles.tab}
                />
              ))}
            </View>
          </View>
        </View>

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
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  splash: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  inner: { flex: 1, width: '100%', maxWidth: 720, alignSelf: 'center', paddingHorizontal: 12 },
  topbar: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, alignItems: 'center', paddingVertical: 8 },
  scroll: { flex: 1 },
  scrollContent: { paddingBottom: 12 },
  dock: { paddingBottom: 8, gap: 6 },
  actions: { flexDirection: 'row', gap: 8, paddingVertical: 8 },
  action: { flex: 1 },
  actionWide: { flex: 1.25 },
  tabs: { flexDirection: 'row', gap: 6 },
  tab: { flex: 1, minHeight: TAP },
});

export type { ViewName };
