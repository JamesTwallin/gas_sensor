// The big state card, the two charts and the environment read-out.

import { batteryPercent } from '../core/simulator';
import type { AppController, UiState } from '../controller';
import { LIVE_SPAN_MS } from '../controller';
import { LiveChart, OverviewChart } from './charts';
import { Legend } from './components';
import { fmtDuration, signed } from './format';
import { Box, Text } from './restyle';
import type { Theme } from './theme';

const CHART_HEIGHT = 140;
const OVERVIEW_HEIGHT = 96;

const kohm = (r: number | null) =>
  r === null ? '—' : r >= 1e6 ? `${(r / 1e6).toFixed(2)} MΩ` : `${(r / 1000).toFixed(1)} kΩ`;

interface CardLook {
  word: string;
  sub: string;
  lpg: string | null;
  bg: string;
  border: string;
  fg: string;
  /** The LOW/MED/HIGH word is the loudest thing on screen; the others are calmer. */
  big: boolean;
  progress: number | null;
}

function cardLook(state: UiState, theme: Theme): CardLook {
  const base = { bg: theme.surface2, border: theme.border, fg: theme.text, big: false, progress: null, lpg: null };
  const out = state.lastOut;
  if (!state.linked || !out) {
    return {
      ...base,
      word: state.linked ? 'WAITING' : 'NOT CONNECTED',
      sub: state.linked ? 'Waiting for data…' : 'Tap Connect to find your sensor',
    };
  }
  if (out.state === 'HEATER_OFF') {
    return {
      ...base,
      border: theme.critical,
      word: 'HEATERS OFF',
      sub: 'Battery cutoff — no valid readings',
    };
  }
  if (out.state === 'WARMUP' || out.state === 'BASELINING') {
    return {
      ...base,
      word: out.state === 'WARMUP' ? 'WARMING UP' : 'BASELINING',
      sub: `${fmtDuration(out.stateDurationMs - out.stateElapsedMs)} left`,
      progress: Math.min(1, out.stateElapsedMs / Math.max(1, out.stateDurationMs)),
    };
  }
  const level = out.ch4.level ?? 'LOW';
  const skin =
    level === 'HIGH'
      ? { bg: theme.critical, border: theme.critical, fg: theme.onDark }
      : level === 'MED'
        ? { bg: theme.warning, border: theme.warning, fg: theme.onLight }
        : { bg: theme.good, border: theme.good, fg: theme.onDark };
  return {
    ...skin,
    big: true,
    progress: null,
    word: out.ch4.level ?? '—',
    sub: `CH4 ${signed(out.ch4.devMv)}`,
    lpg: `LPG ${out.lpg.level ?? '—'} ${signed(out.lpg.devMv)}`,
  };
}

export function LiveScreen({
  state,
  controller,
  theme,
}: {
  state: UiState;
  controller: AppController;
  theme: Theme;
}) {
  const look = cardLook(state, theme);
  const out = state.lastOut;
  const s = state.lastSample;
  const now = controller.chartNow();

  const d = (v: number | null | undefined, digits: number, unit: string) =>
    v === null || v === undefined ? '—' : `${v.toFixed(digits)}${unit}`;
  const cells: [string, string][] = [
    ['CH4 VRL', out ? `${Math.round(out.ch4.voutMv)} mV` : '—'],
    [
      'CH4 baseline',
      out && out.state !== 'WARMUP' && out.state !== 'HEATER_OFF' ? `${Math.round(out.ch4.baselineMv)} mV` : '—',
    ],
    ['CH4 Rs', kohm(state.lastRs.ch4)],
    ['LPG VRL', out ? `${Math.round(out.lpg.voutMv)} mV` : '—'],
    ['LPG Rs', kohm(state.lastRs.lpg)],
    ['Temp', d(s?.tempC, 1, ' °C')],
    ['Humidity', d(s?.humidityPct, 0, ' %')],
    ['Pressure', d(s?.pressureHpa, 1, ' hPa')],
    ['Battery', s ? `${(s.vbatMv / 1000).toFixed(2)} V · ${batteryPercent(s.vbatMv)} %` : '—'],
  ];

  return (
    <Box gap="m">
      {/* Fixed height whatever the state, so WARMUP -> BASELINING -> LOW never moves the charts. */}
      <Box
        height={164}
        justifyContent="center"
        borderRadius="l"
        borderWidth={3}
        paddingHorizontal="l"
        style={{ backgroundColor: look.bg, borderColor: look.border }}
      >
        <Text
          variant="stateWord"
          numberOfLines={1}
          adjustsFontSizeToFit
          style={{ color: look.fg, fontSize: look.big ? 64 : 36, lineHeight: look.big ? 70 : 44 }}
        >
          {look.word}
        </Text>
        <Text variant="stateSub" numberOfLines={1} style={{ color: look.fg }}>
          {look.sub}
        </Text>
        {/* The third line is either the progress bar or the LPG line; the slot is always there. */}
        <Box height={28} justifyContent="center" marginTop="xs">
          {look.progress !== null ? (
            <Box height={12} borderRadius="pill" overflow="hidden" style={{ backgroundColor: theme.bg }}>
              <Box height="100%" style={{ width: `${look.progress * 100}%`, backgroundColor: theme.text }} />
            </Box>
          ) : look.lpg ? (
            <Text variant="stateLine" numberOfLines={1} style={{ color: look.fg, opacity: 0.95 }}>
              {look.lpg}
            </Text>
          ) : null}
        </Box>
      </Box>

      <Box>
        <Legend
          items={[
            ['CH4', theme.ch4],
            ['LPG', theme.lpg],
            ['baseline', theme.baseline],
          ]}
          note="VRL, live"
        />
        <LiveChart
          points={controller.livePoints()}
          now={now}
          spanMs={LIVE_SPAN_MS}
          height={CHART_HEIGHT}
          theme={theme}
        />
      </Box>

      <Box>
        <Legend
          items={[
            ['CH4 peak', theme.ch4],
            ['baseline', theme.baseline],
          ]}
          note={`last ${Math.round(state.settings.classWindowMs / 60000)} min`}
        />
        <OverviewChart
          points={controller.overviewPoints()}
          now={now}
          spanMs={state.settings.classWindowMs}
          fullScaleMv={state.info.vc_mv}
          height={OVERVIEW_HEIGHT}
          theme={theme}
        />
      </Box>

      <Box flexDirection="row" flexWrap="wrap" gap="s">
        {cells.map(([k, v]) => (
          <Box
            key={k}
            flexGrow={1}
            flexBasis="30%"
            borderRadius="s"
            borderWidth={1}
            padding="s"
            gap="xxs"
            style={{ backgroundColor: theme.surface, borderColor: theme.border }}
          >
            <Text variant="cellKey" numberOfLines={1}>
              {k}
            </Text>
            <Text variant="cellValue" numberOfLines={1} adjustsFontSizeToFit>
              {v}
            </Text>
          </Box>
        ))}
      </Box>
    </Box>
  );
}
