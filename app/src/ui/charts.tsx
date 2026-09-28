// The two charts, drawn with react-native-svg. All the geometry is in
// ui/chartPaths.ts (pure); this file is only paint: a gradient wash under CH4,
// 2 px lines, hairline solid grid, an end marker ringed in the surface colour.

import { useState } from 'react';
import { View, type LayoutChangeEvent } from 'react-native';
import Svg, { Circle, Defs, G, Line, LinearGradient, Path, Stop, Text as SvgText } from 'react-native-svg';
import type { ChartPoint } from '../core/chartData';
import {
  DEFAULT_LAYOUT,
  buildLiveChart,
  buildOverviewChart,
  type ChartFrame,
  type ChartLayout,
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

interface LiveChartProps {
  points: readonly ChartPoint[];
  now: number;
  spanMs: number;
  height: number;
  rangeFloorMv: number;
  theme: Theme;
}

export function LiveChart({ points, now, spanMs, height, rangeFloorMv, theme }: LiveChartProps) {
  const [width, onLayout] = useMeasuredWidth();
  if (width <= 0) return <View style={{ width: '100%', height }} onLayout={onLayout} />;
  const layout: ChartLayout = { width, height, ...DEFAULT_LAYOUT };
  const c = buildLiveChart(points, now, spanMs, layout, rangeFloorMv);
  return (
    <View style={{ width: '100%', height }} onLayout={onLayout}>
      <Svg width={width} height={height}>
        <Defs>
          <LinearGradient id="ch4wash" x1="0" y1="0" x2="0" y2="1">
            <Stop offset="0" stopColor={theme.ch4} stopOpacity={0.32} />
            <Stop offset="1" stopColor={theme.ch4} stopOpacity={0.02} />
          </LinearGradient>
        </Defs>
        <Frame frame={c} layout={layout} theme={theme} />
        {c.ch4Areas.map((d, i) => (
          <Path key={`a${i}`} d={d} fill="url(#ch4wash)" />
        ))}
        {c.ch4Lines.map((d, i) => (
          <Path key={`c${i}`} d={d} stroke={theme.ch4} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" fill="none" />
        ))}
        {c.lpgLines.map((d, i) => (
          <Path key={`l${i}`} d={d} stroke={theme.lpg} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" fill="none" />
        ))}
        {c.baselineLines.map((d, i) => (
          <Path
            key={`b${i}`}
            d={d}
            stroke={theme.baseline}
            strokeWidth={1.5}
            strokeDasharray="2,5"
            strokeLinecap="round"
            fill="none"
            opacity={0.8}
          />
        ))}
        <EndMarker at={c.lpgEnd} colour={theme.lpg} surface={theme.surface} />
        <EndMarker at={c.ch4End} colour={theme.ch4} surface={theme.surface} />
      </Svg>
    </View>
  );
}

interface OverviewChartProps {
  points: readonly ChartPoint[];
  now: number;
  spanMs: number;
  height: number;
  rangeFloorMv: number;
  theme: Theme;
}

export function OverviewChart({ points, now, spanMs, height, rangeFloorMv, theme }: OverviewChartProps) {
  const [width, onLayout] = useMeasuredWidth();
  if (width <= 0) return <View style={{ width: '100%', height }} onLayout={onLayout} />;
  const layout: ChartLayout = { width, height, ...DEFAULT_LAYOUT };
  const c = buildOverviewChart(points, now, spanMs, layout, rangeFloorMv);
  return (
    <View style={{ width: '100%', height }} onLayout={onLayout}>
      <Svg width={width} height={height}>
        <Defs>
          <LinearGradient id="ch4washOv" x1="0" y1="0" x2="0" y2="1">
            <Stop offset="0" stopColor={theme.ch4} stopOpacity={0.28} />
            <Stop offset="1" stopColor={theme.ch4} stopOpacity={0.02} />
          </LinearGradient>
        </Defs>
        <Frame frame={c} layout={layout} theme={theme} />
        {c.ch4Areas.map((d, i) => (
          <Path key={`a${i}`} d={d} fill="url(#ch4washOv)" />
        ))}
        {c.ch4Lines.map((d, i) => (
          <Path key={`c${i}`} d={d} stroke={theme.ch4} strokeWidth={2} strokeLinejoin="round" fill="none" />
        ))}
        {c.baselineRule && (
          <Line
            x1={c.baselineRule.x1}
            y1={c.baselineRule.y}
            x2={c.baselineRule.x2}
            y2={c.baselineRule.y}
            stroke={theme.baseline}
            strokeWidth={1.5}
            strokeDasharray="2,5"
            opacity={0.8}
          />
        )}
      </Svg>
    </View>
  );
}
