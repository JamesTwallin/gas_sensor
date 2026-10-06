// The per-channel charts, drawn with react-native-svg. All the geometry is in
// ui/chartPaths.ts (pure); this file is only paint: the first derivative as a
// line on its own axis with zero and the spike threshold ruled, red and heavier
// where it is over the threshold, and the VRL trace as a 2 px line over a gradient wash with hairline
// grid and an end marker ringed in the surface colour.

import { useState } from 'react';
import { View, type LayoutChangeEvent } from 'react-native';
import Svg, { Circle, Defs, G, Line, LinearGradient, Path, Stop, Text as SvgText } from 'react-native-svg';
import type { ChartPoint } from '../core/chartData';
import {
  DEFAULT_LAYOUT,
  DEFAULT_RANGE_FLOOR_MV,
  buildLiveChart,
  buildSlopeChart,
  buildSlopeOverview,
  type ChartFrame,
  type ChartLayout,
  type Series,
  type SlopeChart as SlopeGeometry,
  type XY,
} from './chartPaths';
import { FONT, type Theme } from './theme';

const AXIS_FONT = 11;

/** Stroke and type sizes for the slope charts. */
interface SlopeSizes {
  pad: Pick<ChartLayout, 'padL' | 'padT' | 'padB'>;
  font: number;
  line: number;
  /** The over-threshold stretches of the trace. */
  hotLine: number;
  rule: number;
}

const SLOPE_NORMAL: SlopeSizes = { pad: DEFAULT_LAYOUT, font: AXIS_FONT, line: 1.5, hotLine: 3.5, rule: 1 };
/** Presentation mode: everything a camera has to read is drawn larger. */
const SLOPE_BIG: SlopeSizes = { pad: { padL: 72, padT: 12, padB: 30 }, font: 18, line: 3.5, hotLine: 7, rule: 2 };

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
  series: Series;
  theme: Theme;
}

/** The VRL trace: context for the slope chart above it. */
export function LiveChart({ points, now, spanMs, height, series, theme }: ChartProps) {
  const [width, onLayout] = useMeasuredWidth();
  if (width <= 0) return <View style={{ width: '100%', height }} onLayout={onLayout} />;
  const layout: ChartLayout = { width, height, ...DEFAULT_LAYOUT };
  const c = buildLiveChart(points, now, spanMs, layout, DEFAULT_RANGE_FLOOR_MV, series);
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
        <EndMarker at={c.end} colour={colour} surface={theme.surface} />
      </Svg>
    </View>
  );
}

/** Paint for both slope charts: zero ruled solid, the threshold dashed in red, the trace red and heavier above it. */
function SlopePlot({ c, layout, theme, k }: { c: SlopeGeometry; layout: ChartLayout; theme: Theme; k: SlopeSizes }) {
  const yLabel = (y: number, text: string) => (
    <SvgText x={layout.padL - 8} y={y + k.font / 3} fill={theme.textFaint} fontSize={k.font} fontFamily={FONT.medium} textAnchor="end">
      {text}
    </SvgText>
  );
  const caption = (x: number, text: string, anchor: 'start' | 'end') => (
    <SvgText x={x} y={layout.height - k.font / 3} fill={theme.textFaint} fontSize={k.font} fontFamily={FONT.medium} textAnchor={anchor}>
      {text}
    </SvgText>
  );
  return (
    <Svg width={layout.width} height={layout.height}>
      {c.gridLines.map((g) => (
        <G key={g.y}>
          <Line x1={layout.padL} y1={g.y} x2={layout.width} y2={g.y} stroke={theme.grid} strokeWidth={k.rule} />
          {yLabel(g.y, g.label)}
        </G>
      ))}
      <Line x1={layout.padL} y1={c.zeroY} x2={layout.width} y2={c.zeroY} stroke={theme.axis} strokeWidth={k.rule} />
      {yLabel(c.zeroY, '0')}
      {c.thresholdY !== null && (
        <Line
          x1={layout.padL}
          y1={c.thresholdY}
          x2={layout.width}
          y2={c.thresholdY}
          stroke={theme.critical}
          strokeWidth={k.rule}
          strokeDasharray={`${2 * k.rule},${4 * k.rule}`}
          opacity={0.8}
        />
      )}
      {c.lines.map((d, i) => (
        <Path key={`s${i}`} d={d} stroke={theme.slope} strokeWidth={k.line} strokeLinejoin="round" strokeLinecap="round" fill="none" />
      ))}
      {c.hotLines.map((d, i) => (
        <Path key={`h${i}`} d={d} stroke={theme.critical} strokeWidth={k.hotLine} strokeLinejoin="round" strokeLinecap="round" fill="none" />
      ))}
      {caption(layout.padL, c.leftLabel, 'start')}
      {caption(layout.width - 1, c.rightLabel, 'end')}
    </Svg>
  );
}

type SlopeProps = ChartProps & {
  thresholdMvPerS: number | null;
  /** Presentation mode: thicker strokes and larger labels. */
  big?: boolean;
};

/** The derivative, mV/s, over the live span: the plume indicator. */
export function SlopeChart({ points, now, spanMs, height, series, theme, thresholdMvPerS, big }: SlopeProps) {
  const [width, onLayout] = useMeasuredWidth();
  if (width <= 0) return <View style={{ width: '100%', height }} onLayout={onLayout} />;
  const k = big ? SLOPE_BIG : SLOPE_NORMAL;
  const layout: ChartLayout = { width, height, ...k.pad };
  return (
    <View style={{ width: '100%', height }} onLayout={onLayout}>
      <SlopePlot c={buildSlopeChart(points, now, spanMs, layout, series, thresholdMvPerS)} layout={layout} theme={theme} k={k} />
    </View>
  );
}

/** Peak slope per column over the overview span, same paint as the live slope chart. */
export function SlopeOverviewChart({ points, now, spanMs, height, series, theme, thresholdMvPerS }: SlopeProps) {
  const [width, onLayout] = useMeasuredWidth();
  if (width <= 0) return <View style={{ width: '100%', height }} onLayout={onLayout} />;
  const layout: ChartLayout = { width, height, ...DEFAULT_LAYOUT };
  return (
    <View style={{ width: '100%', height }} onLayout={onLayout}>
      <SlopePlot
        c={buildSlopeOverview(points, now, spanMs, layout, series, thresholdMvPerS)}
        layout={layout}
        theme={theme}
        k={SLOPE_NORMAL}
      />
    </View>
  );
}
