// Presentation mode: the two slopes and nothing else, drawn large enough to
// read in a video of the screen. No header chips, dock or tabs; each channel is
// a figure over its last-60-s slope chart, and the figure's band turns red
// while that channel is spiking.

import { useEffect, useState } from 'react';
import { BackHandler, Pressable, View } from 'react-native';
import type { AppController, UiState } from '../controller';
import { LIVE_SPAN_MS } from '../controller';
import type { ChartPoint } from '../core/chartData';
import type { SpikeResult } from '../core/spike';
import { SlopeChart } from './charts';
import type { Series } from './chartPaths';
import { Icon } from './components';
import { fmtDuration, signed } from './format';
import { Box, Text } from './restyle';
import { FONT, TAP, type Theme } from './theme';

/** Why there is no slope to show, or null when readings are live. */
function idleText(state: UiState): string | null {
  const out = state.lastOut;
  if (!state.linked) return 'Not connected';
  if (state.linkStatus !== 'connected') return state.linkStatus === 'reconnecting' ? 'Reconnecting…' : 'Connecting…';
  if (!out) return 'Waiting for data…';
  if (out.state === 'HEATER_OFF') return 'Heaters off: no valid readings';
  if (out.state === 'WARMUP') return `Warming up · ${fmtDuration(out.stateDurationMs - out.stateElapsedMs)} left`;
  return null;
}

function Panel({
  name,
  series,
  result,
  spiking,
  idle,
  points,
  now,
  theme,
}: {
  name: string;
  series: Series;
  result: SpikeResult;
  spiking: boolean;
  idle: string | null;
  points: readonly ChartPoint[];
  now: number;
  theme: Theme;
}) {
  const [chartHeight, setChartHeight] = useState(0);
  const fg = spiking ? theme.onDark : theme.text;
  const fgMuted = spiking ? 'rgba(255,255,255,0.85)' : theme.textMuted;
  const threshold = result.thresholdMvPerS === null ? '' : `threshold ${Math.round(result.thresholdMvPerS)} mV/s`;
  return (
    <Box flex={1} borderRadius="xl" overflow="hidden" style={{ backgroundColor: theme.surface }}>
      <Box paddingHorizontal="l" paddingTop="m" paddingBottom="s" style={{ backgroundColor: spiking ? theme.critical : theme.surface }}>
        <Box flexDirection="row" alignItems="center" justifyContent="space-between">
          <Text style={{ color: fgMuted, fontFamily: FONT.bold, fontSize: 20, letterSpacing: 1.5 }}>{name.toUpperCase()}</Text>
          {spiking && <Text style={{ color: fg, fontFamily: FONT.extrabold, fontSize: 22, letterSpacing: 1.5 }}>SPIKE</Text>}
        </Box>
        <Box flexDirection="row" alignItems="baseline" gap="s">
          <Text
            variant="stateWord"
            numberOfLines={1}
            adjustsFontSizeToFit
            flexShrink={1}
            style={{ color: fg, fontSize: 96, lineHeight: 104, fontVariant: ['tabular-nums'] }}
          >
            {idle !== null || result.slopeMvPerS === null ? '—' : signed(result.slopeMvPerS)}
          </Text>
          <Text style={{ color: fgMuted, fontFamily: FONT.semibold, fontSize: 26 }}>mV/s</Text>
        </Box>
        <Text numberOfLines={1} style={{ color: fgMuted, fontFamily: FONT.medium, fontSize: 18 }}>
          {idle ?? threshold}
        </Text>
      </Box>
      <View
        style={{ flex: 1, paddingHorizontal: 8, paddingBottom: 8 }}
        onLayout={(e) => setChartHeight(Math.floor(e.nativeEvent.layout.height) - 8)}
      >
        {chartHeight > 60 && (
          <SlopeChart
            big
            points={points}
            now={now}
            spanMs={LIVE_SPAN_MS}
            height={chartHeight}
            series={series}
            theme={theme}
            thresholdMvPerS={result.thresholdMvPerS}
          />
        )}
      </View>
    </Box>
  );
}

export function PresentScreen({
  state,
  controller,
  theme,
  onExit,
}: {
  state: UiState;
  controller: AppController;
  theme: Theme;
  onExit: () => void;
}) {
  // Android back leaves presentation mode rather than the app.
  useEffect(() => {
    const sub = BackHandler.addEventListener('hardwareBackPress', () => {
      onExit();
      return true;
    });
    return () => sub.remove();
  }, [onExit]);

  const idle = idleText(state);
  const points = controller.livePoints();
  const now = controller.chartNow();
  const { spikes } = state;
  const caption =
    (state.linkName ?? 'No sensor') + (state.recording ? ` · REC ${fmtDuration(Date.now() - state.recStartedAt)}` : '');

  return (
    <Box flex={1} paddingHorizontal="m" paddingBottom="m" gap="m">
      <Box flexDirection="row" alignItems="center" justifyContent="space-between" height={TAP}>
        <Text variant="chip" numberOfLines={1} flexShrink={1} paddingLeft="xs">
          {caption}
        </Text>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Leave presentation mode"
          onPress={onExit}
          hitSlop={8}
          style={{ width: TAP, height: TAP, alignItems: 'center', justifyContent: 'center' }}
        >
          <Icon name="close" size={24} color={theme.textMuted} />
        </Pressable>
      </Box>
      <Panel
        name="Methane"
        series="ch4"
        result={spikes.ch4}
        spiking={idle === null && spikes.active.ch4}
        idle={idle}
        points={points}
        now={now}
        theme={theme}
      />
      <Panel
        name="LP gas"
        series="lpg"
        result={spikes.lpg}
        spiking={idle === null && spikes.active.lpg}
        idle={idle}
        points={points}
        now={now}
        theme={theme}
      />
    </Box>
  );
}
