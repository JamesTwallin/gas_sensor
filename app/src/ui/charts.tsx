// The per-channel charts, drawn with react-native-svg. All the geometry is in
// ui/chartPaths.ts (pure); this file is only paint: a gradient wash under the
// trace, a 2 px line, hairline solid grid, an end marker ringed in the surface
// colour, the first derivative as a thin line on its own axis, spikes marked.

import { useState } from 'react';
import { View, type LayoutChangeEvent } from 'react-native';
import Svg, { Circle, Defs, G, Line, LinearGradient, Path, Stop, Text as SvgText } from 'react-native-svg';
import type { ChartPoint } from '../core/chartData';
import {
  DEFAULT_LAYOUT,
  buildLiveChart,
  buildOverviewChart,
  buildSlopeChart,
  type ChartFrame,
  type ChartLayout,
  type Series,
  type XY,
} from './chartPaths';
import { FONT, type Theme } from './theme';

const AXIS_FONT = 11;

interface FrameProps {
  frame: ChartFrame;
  layout: ChartLayout;
  theme: Theme;
}

/** Hairline grid with labels, the plot floor, and the two time captions. */
function Frame({ frame, layout, theme }: FrameProps) {
  return (
    <G>
      {frame.gridLines.map((g) => (
        <G key={g.y}>
          <Line x1={layout.padL} y1={g.y} x2={layout.width} y2={g.y} stroke={theme.grid} strokeWidth={1} />
          <SvgText
            x={layout.padL - 6}
            y={g.y + AXIS_FONT / 3}
            fill={theme.textFaint}
            fontSize={AXIS_FONT}
            fontFamily={FONT.medium}
            textAnchor="end"
          >
            {g.label}
          </SvgText>
        </G>
      ))}
      <Line x1={layout.padL} y1={frame.axisY} x2={layout.width} y2={frame.axisY} stroke={theme.axis} strokeWidth={1} />
      <SvgText x={layout.padL} y={layout.height - 3} fill={theme.textFaint} fontSize={AXIS_FONT} fontFamily={FONT.medium}>
        {frame.leftLabel}
      </SvgText>
      <SvgText
        x={layout.width - 1}
        y={layout.height - 3}
        fill={theme.textFaint}
        fontSize={AXIS_FONT}
        fontFamily={FONT.medium}
        textAnchor="end"
      >
        {frame.rightLabel}
      </SvgText>
    </G>
  );
}

function EndMarker({ at, colour, surface }: { at: XY | null; colour: string; surface: string }) {
  if (!at) return null;
  return <Circle cx={at.x} cy={at.y} r={4} fill={colour} stroke={surface} strokeWidth={2} />;
}

/** Measure the available width, then render at that size. */
function useMeasuredWidth(): [number, (e: LayoutChangeEvent) => void] {
  const [width, setWidth] = useState(0);
  return [
    width,
    (e: LayoutChangeEvent) => {
      const w = Math.round(e.nativeEvent.layout.width);
      if (w !== width) setWidth(w);
    },
  ];
}

interface ChartProps {
  points: readonly ChartPoint[];
  now: number;
  spanMs: number;
  height: number;
  rangeFloorMv: number;
  series: Series;
  theme: Theme;
}

export function LiveChart({ points, now, spanMs, height, rangeFloorMv, series, theme }: ChartProps) {
  const [width, onLayout] = useMeasuredWidth();
  if (width <= 0) return <View style={{ width: '100%', height }} onLayout={onLayout} />;
  const layout: ChartLayout = { width, height, ...DEFAULT_LAYOUT };
  const c = buildLiveChart(points, now, spanMs, layout, rangeFloorMv, series);
  const colour = theme[series];
  const washId = `wash-live-${series}`;
  return (
    <View style={{ width: '100%', height }} onLayout={onLayout}>
      <Svg width={width} height={height}>
        <Defs>
          <LinearGradient id={washId} x1="0" y1="0" x2="0" y2="1">
            <Stop offset="0" stopColor={colour} stopOpacity={0.32} />
            <Stop offset="1" stopColor={colour} stopOpacity={0.02} />
          </LinearGradient>
        </Defs>
        <Frame frame={c} layout={layout} theme={theme} />
        {c.areas.map((d, i) => (
          <Path key={`a${i}`} d={d} fill={`url(#${washId})`} />
        ))}
        {c.lines.map((d, i) => (
          <Path key={`l${i}`} d={d} stroke={colour} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" fill="none" />
        ))}
        {c.spikeMarks.map((m, i) => (
          <Circle key={`k${i}`} cx={m.x} cy={m.y} r={4} fill={theme.critical} stroke={theme.surface} strokeWidth={1.5} />
        ))}
        <EndMarker at={c.end} colour={colour} surface={theme.surface} />
      </Svg>
    </View>
  );
}

/**
 * The derivative panel: sits directly under LiveChart, same time axis, its own
 * y-limits. Zero ruled solid, the spike threshold ruled dotted in red, flagged
 * samples marked.
 */
export function SlopeChart({
  points,
  now,
  spanMs,
  height,
  series,
  theme,
  thresholdMvPerS,
}: Omit<ChartProps, 'rangeFloorMv'> & { thresholdMvPerS: number | null }) {
  const [width, onLayout] = useMeasuredWidth();
  if (width <= 0) return <View style={{ width: '100%', height }} onLayout={onLayout} />;
  const layout: ChartLayout = { width, height, ...DEFAULT_LAYOUT };
  const c = buildSlopeChart(points, now, spanMs, layout, series, thresholdMvPerS);
  return (
    <View style={{ width: '100%', height }} onLayout={onLayout}>
      <Svg width={width} height={height}>
        {c.gridLines.map((g) => (
          <G key={g.y}>
            <Line x1={layout.padL} y1={g.y} x2={layout.width} y2={g.y} stroke={theme.grid} strokeWidth={1} />
            <SvgText
              x={layout.padL - 6}
              y={g.y + AXIS_FONT / 3}
              fill={theme.textFaint}
              fontSize={AXIS_FONT}
              fontFamily={FONT.medium}
              textAnchor="end"
            >
              {g.label}
            </SvgText>
          </G>
        ))}
        <Line x1={layout.padL} y1={c.zeroY} x2={layout.width} y2={c.zeroY} stroke={theme.axis} strokeWidth={1} />
        <SvgText x={layout.padL - 6} y={c.zeroY + AXIS_FONT / 3} fill={theme.textFaint} fontSize={AXIS_FONT} fontFamily={FONT.medium} textAnchor="end">
          0
        </SvgText>
        {c.thresholdY !== null && (
          <Line
            x1={layout.padL}
            y1={c.thresholdY}
            x2={layout.width}
            y2={c.thresholdY}
            stroke={theme.critical}
            strokeWidth={1}
            strokeDasharray="2,4"
            opacity={0.8}
          />
        )}
        {c.lines.map((d, i) => (
          <Path key={`s${i}`} d={d} stroke={theme.slope} strokeWidth={1.5} strokeLinejoin="round" fill="none" />
        ))}
        {c.spikeMarks.map((m, i) => (
          <Circle key={`k${i}`} cx={m.x} cy={m.y} r={3.5} fill={theme.critical} stroke={theme.surface} strokeWidth={1.5} />
        ))}
        <SvgText x={layout.padL} y={layout.height - 3} fill={theme.textFaint} fontSize={AXIS_FONT} fontFamily={FONT.medium}>
          {c.leftLabel}
        </SvgText>
        <SvgText x={layout.width - 1} y={layout.height - 3} fill={theme.textFaint} fontSize={AXIS_FONT} fontFamily={FONT.medium} textAnchor="end">
          {c.rightLabel}
        </SvgText>
      </Svg>
    </View>
  );
}

export function OverviewChart({ points, now, spanMs, height, rangeFloorMv, series, theme }: ChartProps) {
  const [width, onLayout] = useMeasuredWidth();
  if (width <= 0) return <View style={{ width: '100%', height }} onLayout={onLayout} />;
  const layout: ChartLayout = { width, height, ...DEFAULT_LAYOUT };
  const c = buildOverviewChart(points, now, spanMs, layout, rangeFloorMv, series);
  const colour = theme[series];
  const washId = `wash-overview-${series}`;
  return (
    <View style={{ width: '100%', height }} onLayout={onLayout}>
      <Svg width={width} height={height}>
        <Defs>
          <LinearGradient id={washId} x1="0" y1="0" x2="0" y2="1">
            <Stop offset="0" stopColor={colour} stopOpacity={0.28} />
            <Stop offset="1" stopColor={colour} stopOpacity={0.02} />
          </LinearGradient>
        </Defs>
        <Frame frame={c} layout={layout} theme={theme} />
        {c.areas.map((d, i) => (
          <Path key={`a${i}`} d={d} fill={`url(#${washId})`} />
        ))}
        {c.lines.map((d, i) => (
          <Path key={`l${i}`} d={d} stroke={colour} strokeWidth={2} strokeLinejoin="round" fill="none" />
        ))}
        {/* Spike ticks along the top edge: one per 2 px column with a flagged sample. */}
        {c.spikeTicks.map((x, i) => (
          <Line key={`t${i}`} x1={x} y1={layout.padT} x2={x} y2={layout.padT + 7} stroke={theme.critical} strokeWidth={2} />
        ))}
      </Svg>
    </View>
  );
}
