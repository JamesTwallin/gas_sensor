// The rev A OLED chart design, scaled up for a phone, drawn with react-native-svg.
// All the geometry is in ui/chartPaths.ts (pure); this file is only paint.

import { useState } from 'react';
import { StyleSheet, View, type LayoutChangeEvent } from 'react-native';
import Svg, { G, Line, Path, Text as SvgText } from 'react-native-svg';
import type { ChartPoint } from '../core/chartData';
import {
  DEFAULT_LAYOUT,
  buildLiveChart,
  buildOverviewChart,
  type ChartFrame,
  type ChartLayout,
} from './chartPaths';
import type { Theme } from './theme';

const AXIS_FONT = 12;

interface FrameProps {
  frame: ChartFrame;
  layout: ChartLayout;
  theme: Theme;
}

/** Dashed 1 V grid with labels, the 0 mV axis, and the two time captions. */
function Frame({ frame, layout, theme }: FrameProps) {
  return (
    <G>
      {frame.gridLines.map((g) => (
        <G key={g.y}>
          <Line
            x1={layout.padL}
            y1={g.y}
            x2={layout.width}
            y2={g.y}
            stroke={theme.grid}
            strokeWidth={1}
            strokeDasharray="4,6"
          />
          <SvgText
            x={layout.padL - 5}
            y={g.y + AXIS_FONT / 3}
            fill={theme.textMuted}
            fontSize={AXIS_FONT}
            textAnchor="end"
          >
            {g.label}
          </SvgText>
        </G>
      ))}
      <Line
        x1={layout.padL}
        y1={frame.axisY}
        x2={layout.width}
        y2={frame.axisY}
        stroke={theme.axis}
        strokeWidth={1}
      />
      <SvgText x={layout.padL} y={layout.height - 4} fill={theme.textMuted} fontSize={AXIS_FONT}>
        {frame.leftLabel}
      </SvgText>
      <SvgText
        x={layout.width - 2}
        y={layout.height - 4}
        fill={theme.textMuted}
        fontSize={AXIS_FONT}
        textAnchor="end"
      >
        {frame.rightLabel}
      </SvgText>
    </G>
  );
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
  theme: Theme;
}

export function LiveChart({ points, now, spanMs, height, theme }: LiveChartProps) {
  const [width, onLayout] = useMeasuredWidth();
  if (width <= 0) return <View style={[styles.box, { height }]} onLayout={onLayout} />;
  const layout: ChartLayout = { width, height, ...DEFAULT_LAYOUT };
  const c = buildLiveChart(points, now, spanMs, layout);
  return (
    <View style={[styles.box, { height }]} onLayout={onLayout}>
      <Svg width={width} height={height}>
        <Frame frame={c} layout={layout} theme={theme} />
        {c.ch4Areas.map((d, i) => (
          <Path key={`a${i}`} d={d} fill={theme.ch4} fillOpacity={0.35} />
        ))}
        {c.ch4Lines.map((d, i) => (
          <Path key={`c${i}`} d={d} stroke={theme.ch4} strokeWidth={2} strokeLinejoin="round" fill="none" />
        ))}
        {c.lpgLines.map((d, i) => (
          <Path key={`l${i}`} d={d} stroke={theme.lpg} strokeWidth={2} strokeLinejoin="round" fill="none" />
        ))}
        {c.baselineLines.map((d, i) => (
          <Path
            key={`b${i}`}
            d={d}
            stroke={theme.baseline}
            strokeWidth={2}
            strokeDasharray="2,5"
            strokeLinecap="round"
            fill="none"
          />
        ))}
      </Svg>
    </View>
  );
}

interface OverviewChartProps {
  points: readonly ChartPoint[];
  now: number;
  spanMs: number;
  fullScaleMv: number;
  height: number;
  theme: Theme;
}

export function OverviewChart({ points, now, spanMs, fullScaleMv, height, theme }: OverviewChartProps) {
  const [width, onLayout] = useMeasuredWidth();
  if (width <= 0) return <View style={[styles.box, { height }]} onLayout={onLayout} />;
  const layout: ChartLayout = { width, height, ...DEFAULT_LAYOUT };
  const c = buildOverviewChart(points, now, spanMs, fullScaleMv, layout);
  return (
    <View style={[styles.box, { height }]} onLayout={onLayout}>
      <Svg width={width} height={height}>
        <Frame frame={c} layout={layout} theme={theme} />
        {c.ch4Areas.map((d, i) => (
          <Path key={`a${i}`} d={d} fill={theme.ch4} fillOpacity={0.25} />
        ))}
        {c.ch4Lines.map((d, i) => (
          <Path key={`c${i}`} d={d} stroke={theme.ch4} strokeWidth={2} fill="none" />
        ))}
        {c.baselineRule && (
          <Line
            x1={c.baselineRule.x1}
            y1={c.baselineRule.y}
            x2={c.baselineRule.x2}
            y2={c.baselineRule.y}
            stroke={theme.baseline}
            strokeWidth={2}
            strokeDasharray="2,5"
          />
        )}
      </Svg>
    </View>
  );
}

const styles = StyleSheet.create({
  box: { width: '100%' },
});
