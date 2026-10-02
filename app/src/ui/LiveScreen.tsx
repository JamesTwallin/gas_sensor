// The hero state card, the two chart cards and the read-out tiles.

import { TGS2610, TGS2611, fmtPpm } from '../core/ppm';
import { batteryPercent } from '../core/simulator';
import type { AppController, UiState } from '../controller';
import { LIVE_SPAN_MS, OVERVIEW_SPAN_MS } from '../controller';
import { LiveChart, SlopeChart, SlopeOverviewChart } from './charts';
import { Card, Legend, Tile } from './components';
import { fmtDuration, signed } from './format';
import { Box, Text } from './restyle';
import type { Theme } from './theme';

const SLOPE_HEIGHT = 132;
const VRL_HEIGHT = 96;
const OVERVIEW_HEIGHT = 76;

const kohm = (r: number | null): [string, string] =>
  r === null ? ['—', ''] : r >= 1e6 ? [(r / 1e6).toFixed(2), 'MΩ'] : [(r / 1000).toFixed(1), 'kΩ'];

interface CardLook {
  eyebrow: string;
  word: string;
  sub: string;
  lpg: string | null;
  bg: string;
  fg: string;
  fgMuted: string;
  border: string;
  /** The slope figure is the loudest thing on screen; the other states are calmer. */
  big: boolean;
  progress: number | null;
}

function cardLook(state: UiState, theme: Theme): CardLook {
  const quiet = {
    bg: theme.surface,
    fg: theme.text,
    fgMuted: theme.textMuted,
    border: theme.surface,
    big: false,
    progress: null,
    lpg: null,
  };
  const out = state.lastOut;
  if (!state.linked || !out) {
    return {
      ...quiet,
      eyebrow: 'Sensor',
      word: state.linked ? 'WAITING' : 'NOT CONNECTED',
      sub: state.linked ? 'Waiting for data…' : 'No sensor linked',
    };
  }
  if (out.state === 'HEATER_OFF') {
    return {
      ...quiet,
      border: theme.critical,
      eyebrow: 'Sensor',
      word: 'HEATERS OFF',
      sub: 'Battery cutoff — no valid readings',
    };
  }
  if (out.state === 'WARMUP') {
    return {
      ...quiet,
      eyebrow: 'Heater warm-up',
      word: 'WARMING UP',
      sub: `${fmtDuration(out.stateDurationMs - out.stateElapsedMs)} left`,
      progress: Math.min(1, out.stateElapsedMs / Math.max(1, out.stateDurationMs)),
    };
  }
  // RUNNING: the CH4 slope is the reading. The card stays neutral and turns red
  // while the slope is over the spike threshold (held for SPIKE_HOLD_MS).
  const { ch4, lpg, active } = state.spikes;
  const skin = active.ch4
    ? { bg: theme.critical, fg: theme.onDark, fgMuted: 'rgba(255,255,255,0.8)', border: theme.critical }
    : {};
  return {
    ...quiet,
    ...skin,
    big: true,
    eyebrow: active.ch4 ? 'CH4 slope · spike' : 'CH4 slope',
    word: ch4.slopeMvPerS === null ? '—' : signed(ch4.slopeMvPerS),
    sub: ch4.thresholdMvPerS === null ? 'mV/s' : `mV/s · threshold ${Math.round(ch4.thresholdMvPerS)}`,
    lpg: `LPG ${lpg.slopeMvPerS === null ? '—' : signed(lpg.slopeMvPerS)} mV/s${active.lpg ? ' · spike' : ''}`,
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

  const num = (v: number | null | undefined, digits: number) =>
    v === null || v === undefined ? '—' : v.toFixed(digits);
  const [ch4Rs, ch4RsUnit] = kohm(state.lastRs.ch4);
  const [lpgRs, lpgRsUnit] = kohm(state.lastRs.lpg);

  return (
    <Box gap="m">
      {/* Fixed height whatever the state, so WARMUP -> RUNNING never moves the charts. */}
      <Box
        height={172}
        justifyContent="center"
        borderRadius="xl"
        borderWidth={2}
        paddingHorizontal="l"
        style={{ backgroundColor: look.bg, borderColor: look.border }}
      >
        <Text variant="eyebrow" numberOfLines={1} style={{ color: look.fgMuted }}>
          {look.eyebrow}
        </Text>
        <Text
          variant="stateWord"
          numberOfLines={1}
          adjustsFontSizeToFit
          style={{ color: look.fg, fontSize: look.big ? 68 : 34, lineHeight: look.big ? 74 : 42 }}
        >
          {look.word}
        </Text>
        <Text variant="stateSub" numberOfLines={1} style={{ color: look.fg }}>
          {look.sub}
        </Text>
        {/* The third line is either the progress bar or the LPG line; the slot is always there. */}
        <Box height={26} justifyContent="center" marginTop="xs">
          {look.progress !== null ? (
            <Box height={8} borderRadius="pill" overflow="hidden" style={{ backgroundColor: theme.surface2 }}>
              <Box height="100%" borderRadius="pill" style={{ width: `${look.progress * 100}%`, backgroundColor: theme.accent }} />
            </Box>
          ) : look.lpg ? (
            <Text variant="stateLine" numberOfLines={1} style={{ color: look.fgMuted }}>
              {look.lpg}
            </Text>
          ) : null}
        </Box>
      </Box>

      {/* One card per channel: they respond with different slopes, so each gets
          its own axes. Slope first (it is the reading), the VRL trace under it
          for context, then the peak slope over the longer window. */}
      {(
        [
          ['ch4', 'Methane', 'CH4'],
          ['lpg', 'LP gas', 'LPG'],
        ] as const
      ).map(([series, name, short]) => (
        <Card
          key={series}
          theme={theme}
          title={`${name} slope · mV/s`}
          right={
            <Legend
              items={[
                ['slope', theme.slope],
                ['spike', theme.critical],
                [`${short} VRL`, theme[series]],
              ]}
            />
          }
        >
          <SlopeChart
            points={controller.livePoints()}
            now={now}
            spanMs={LIVE_SPAN_MS}
            height={SLOPE_HEIGHT}
            series={series}
            theme={theme}
            thresholdMvPerS={state.spikes[series].thresholdMvPerS}
          />
          <Text variant="tileKey" paddingTop="xs">
            {`${short} VRL`}
          </Text>
          <LiveChart
            points={controller.livePoints()}
            now={now}
            spanMs={LIVE_SPAN_MS}
            height={VRL_HEIGHT}
            series={series}
            theme={theme}
          />
          <Text variant="tileKey" paddingTop="xs">
            {`Peak slope · last ${Math.round(OVERVIEW_SPAN_MS / 60000)} min`}
          </Text>
          <SlopeOverviewChart
            points={controller.overviewPoints()}
            now={now}
            spanMs={OVERVIEW_SPAN_MS}
            height={OVERVIEW_HEIGHT}
            series={series}
            theme={theme}
            thresholdMvPerS={state.spikes[series].thresholdMvPerS}
          />
        </Card>
      ))}

      <Box gap="s">
        <Text variant="eyebrow" paddingLeft="xs">
          Gas
        </Text>
        <Box flexDirection="row" flexWrap="wrap" gap="s">
          <Tile theme={theme} label="CH4 VRL" value={out ? String(Math.round(out.ch4.voutMv)) : '—'} unit="mV" />
          <Tile theme={theme} label="CH4 Rs" value={ch4Rs} unit={ch4RsUnit} />
          <Tile theme={theme} label="LPG VRL" value={out ? String(Math.round(out.lpg.voutMv)) : '—'} unit="mV" />
          <Tile theme={theme} label="LPG Rs" value={lpgRs} unit={lpgRsUnit} />
        </Box>
      </Box>

      <Box gap="s">
        <Box flexDirection="row" alignItems="baseline" justifyContent="space-between" paddingHorizontal="xs">
          <Text variant="eyebrow">Spike detector</Text>
          <Text variant="legend" numberOfLines={1}>
            {state.spikes.count ? `${state.spikes.count} this session · last ${state.spikes.lastText}` : 'no spikes yet'}
          </Text>
        </Box>
        <Box flexDirection="row" flexWrap="wrap" gap="s">
          <Tile
            theme={theme}
            label={state.spikes.ch4.spike ? 'CH4 slope · SPIKE' : 'CH4 slope'}
            value={state.spikes.ch4.slopeMvPerS === null ? '—' : signed(state.spikes.ch4.slopeMvPerS)}
            unit="mV/s"
          />
          <Tile
            theme={theme}
            label={state.spikes.lpg.spike ? 'LPG slope · SPIKE' : 'LPG slope'}
            value={state.spikes.lpg.slopeMvPerS === null ? '—' : signed(state.spikes.lpg.slopeMvPerS)}
            unit="mV/s"
          />
          <Tile
            theme={theme}
            label="Threshold"
            value={state.spikes.ch4.thresholdMvPerS === null ? '—' : String(Math.round(state.spikes.ch4.thresholdMvPerS))}
            unit="mV/s"
          />
        </Box>
      </Box>

      <Box gap="s">
        <Box flexDirection="row" alignItems="baseline" justifyContent="space-between" paddingHorizontal="xs">
          <Text variant="eyebrow">Concentration</Text>
          <Text variant="legend" numberOfLines={1}>
            {state.calibration.ch4 || state.calibration.lpg ? 'datasheet curve, calibrated' : 'datasheet curve, uncalibrated'}
          </Text>
        </Box>
        <Box flexDirection="row" flexWrap="wrap" gap="s">
          <Tile theme={theme} label="Methane" value={fmtPpm(state.lastPpm.ch4, TGS2611)} unit="ppm" />
          <Tile theme={theme} label="LP gas (as iso-butane)" value={fmtPpm(state.lastPpm.lpg, TGS2610)} unit="ppm" />
        </Box>
      </Box>

      <Box gap="s">
        <Text variant="eyebrow" paddingLeft="xs">
          Environment
        </Text>
        <Box flexDirection="row" flexWrap="wrap" gap="s">
          <Tile theme={theme} label="Temperature" value={num(s?.tempC, 1)} unit="°C" />
          <Tile theme={theme} label="Humidity" value={num(s?.humidityPct, 0)} unit="%" />
          <Tile theme={theme} label="Pressure" value={num(s?.pressureHpa, 1)} unit="hPa" />
        </Box>
      </Box>

      <Box gap="s">
        <Text variant="eyebrow" paddingLeft="xs">
          Power
        </Text>
        <Box flexDirection="row" flexWrap="wrap" gap="s">
          {/* Below 3 V no LiPo is fitted: VBAT is 0 (no ADS1115) or a floating input. */}
          <Tile theme={theme} label="Battery" value={s && s.vbatMv >= 3000 ? (s.vbatMv / 1000).toFixed(2) : '—'} unit="V" />
          <Tile theme={theme} label="Charge" value={s && s.vbatMv >= 3000 ? String(batteryPercent(s.vbatMv)) : '—'} unit="%" />
          <Tile theme={theme} label="Heater rail" value={state.info.heater_mv ? (state.info.heater_mv / 1000).toFixed(2) : '—'} unit="V" />
        </Box>
      </Box>
    </Box>
  );
}
