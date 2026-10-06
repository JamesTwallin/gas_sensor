// Live survey map: the recording's GPS track over satellite imagery as a
// heatmap, the phone version of tools/plot_map.py drawn as you walk.
//
// Raw shows the mean CH4 VRL in each ground cell; Spikes shows the steepest
// CH4 rise (mV/s) in each cell, like plot_map.py --deriv. Both use the same
// continuous inferno gradient, scaled to the cells on the map, with a colour
// bar giving the range. Tap a cell to read its value. The geometry and colours
// live in core/mapView.ts, core/track.ts and core/heatmap.ts (unit-tested).
//
// No native map SDK: tiles are plain Images and the overlay is
// react-native-svg, so it runs in Expo Go too and needs no API key. The view
// fits the whole track plus your position until you drag or zoom; the GPS
// button centres on you and follows you as you walk.

import { memo, useCallback, useMemo, useRef, useState } from 'react';
import { Image, PanResponder, Pressable, View, type GestureResponderEvent, type LayoutChangeEvent } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Svg, { Circle, Defs, LinearGradient, Path, Rect, Stop } from 'react-native-svg';
import type { UiState } from '../controller';
import {
  binCells,
  cellAt,
  cellMetres,
  cellRects,
  heatColour,
  heatRange,
  metresPerUnit,
  type HeatCell,
  type HeatMode,
} from '../core/heatmap';
import {
  SINGLE_POINT_ZOOM,
  clampZoom,
  ESRI_ATTRIBUTION,
  esriImageryUrl,
  fitView,
  fromScreen,
  lonLatToMerc,
  panBy,
  toScreen,
  visibleTiles,
  worldPx,
  zoomAbout,
  type MapView,
  type Merc,
  type Size,
} from '../core/mapView';
import { routePaths, type TrackPoint } from '../core/track';
import { Icon, SegmentedTabs, type IconName } from './components';
import { Box, Text, spacing } from './restyle';
import { TAP, type Theme } from './theme';

const FIT_PAD_PX = 36;
const CELL_OPACITY = 0.85;
/** A touch that moves less than this is a tap, not a drag. */
const TAP_SLOP_PX = 8;

const MODES: { key: HeatMode; label: string; icon: IconName }[] = [
  { key: 'raw', label: 'Raw', icon: 'chart-bell-curve' },
  { key: 'spikes', label: 'Spikes', icon: 'chart-line-variant' },
];

/** Tiles only change when the view or size does, not on every sample. */
const Tiles = memo(function Tiles({ view, size }: { view: MapView; size: Size }) {
  const tiles = useMemo(() => visibleTiles(view, size), [view, size]);
  return (
    <>
      {tiles.map((t) => (
        <Image
          key={t.key}
          source={{ uri: esriImageryUrl(t) }}
          fadeDuration={0}
          style={{
            position: 'absolute',
            left: t.left,
            top: t.top,
            // A hair of overlap hides the seams between scaled tiles.
            width: t.size + 0.5,
            height: t.size + 0.5,
          }}
        />
      ))}
    </>
  );
});

function MapButton({
  icon,
  onPress,
  label,
  theme,
  active,
}: {
  icon: IconName;
  onPress: () => void;
  label: string;
  theme: Theme;
  active?: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={onPress}
      hitSlop={6}
      style={({ pressed }) => ({
        width: TAP - 6,
        height: TAP - 6,
        borderRadius: 12,
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: active ? theme.accent : theme.surface,
        opacity: pressed ? 0.75 : 0.92,
      })}
    >
      <Icon name={icon} size={22} color={active ? theme.onDark : theme.text} />
    </Pressable>
  );
}

function touchDistance(e: GestureResponderEvent): number | null {
  const t = e.nativeEvent.touches;
  if (t.length < 2) return null;
  return Math.hypot(t[0].pageX - t[1].pageX, t[0].pageY - t[1].pageY);
}

function fmtValue(v: number, mode: HeatMode): string {
  if (mode === 'raw') return `${Math.round(v)} mV`;
  const r = Math.round(v);
  return `${r > 0 ? '+' : r < 0 ? '−' : ''}${Math.abs(r)} mV/s`;
}

/** Colour bar: the gradient with its two ends labelled. */
function ColourBar({ lo, hi, mode, theme }: { lo: string; hi: string; mode: HeatMode; theme: Theme }) {
  const [w, setW] = useState(0);
  const stops = Array.from({ length: 11 }, (_, i) => i / 10);
  return (
    <Box gap="xxs">
      <View style={{ height: 12 }} onLayout={(e) => setW(e.nativeEvent.layout.width)}>
        {w > 0 && (
          <Svg width={w} height={12}>
            <Defs>
              <LinearGradient id="heat" x1="0" y1="0" x2="1" y2="0">
                {stops.map((t) => (
                  <Stop key={t} offset={t} stopColor={heatColour(t)} />
                ))}
              </LinearGradient>
            </Defs>
            <Rect x={0} y={0} width={w} height={12} rx={6} fill="url(#heat)" />
          </Svg>
        )}
      </View>
      <Box flexDirection="row" justifyContent="space-between">
        <Text variant="legend">{lo}</Text>
        <Text variant="legend" style={{ color: theme.textMuted }}>
          {mode === 'raw' ? 'mean CH4 VRL per cell' : 'steepest CH4 rise per cell'}
        </Text>
        <Text variant="legend">{hi}</Text>
      </Box>
    </Box>
  );
}

export function SurveyMap({
  state,
  points,
  theme,
  height,
  mode,
  onModeChange,
  fullscreen = false,
  onToggleFullscreen,
}: {
  state: UiState;
  /** The track; re-read whenever state.trackTick changes. */
  points: readonly TrackPoint[];
  theme: Theme;
  /** Map height in the page; ignored full screen, where the map fills the space. */
  height: number;
  /** Raw or Spikes; owned by the screen so it carries into and out of full screen. */
  mode: HeatMode;
  onModeChange: (m: HeatMode) => void;
  /** Laid out to fill a full-screen modal: map on top, toggle and colour bar below. */
  fullscreen?: boolean;
  onToggleFullscreen?: () => void;
}) {
  const insets = useSafeAreaInsets();
  const [size, setSize] = useState<Size | null>(null);
  // Who drives the view, in priority order: a drag or pinch (manual), the GPS
  // button (follow you, centred, at this zoom), else fit the whole track.
  const [manual, setManual] = useState<MapView | null>(null);
  const [followZoom, setFollowZoom] = useState<number | null>(null);
  // The tapped cell, kept as its map position so it stays put while panning.
  const [picked, setPicked] = useState<Merc | null>(null);
  const boxRef = useRef<View>(null);
  const onLayout = useCallback((e: LayoutChangeEvent) => {
    const { width, height: h } = e.nativeEvent.layout;
    setSize((s) => (s && s.width === width && s.height === h ? s : { width, height: h }));
  }, []);

  const fix = state.gpsFix;
  const here: Merc | null = fix ? lonLatToMerc(fix.lon, fix.lat) : null;

  // Fit mode: the whole track plus where you are now. trackTick and the fix
  // position are what change it (points is the controller's live array).
  const auto = useMemo(() => {
    if (!size) return null;
    const pts: Merc[] = [...points];
    if (here) pts.push(here);
    return fitView(pts, size, FIT_PAD_PX);
  }, [size, state.trackTick, here?.mx, here?.my]);
  const view: MapView | null =
    manual ?? (followZoom !== null && here ? { cx: here.mx, cy: here.my, zoom: followZoom } : auto);
  const following = !manual && followZoom !== null && !!here;

  // Heatmap: cells sized for the zoom, binned at the track's latitude.
  const lat = points.length ? points[0].lat : (fix?.lat ?? 0);
  const cellM = view ? cellMetres(view.zoom, lat) : 5;
  const cells = useMemo(() => binCells(points, mode, cellM, lat), [state.trackTick, mode, cellM, lat]);
  const threshold = state.spikes.ch4.thresholdMvPerS ?? state.settings.spikeThresholdMvPerS;
  const range = useMemo(() => heatRange(cells, mode, threshold), [cells, mode, threshold]);
  const rects = useMemo(
    () => (view && size && range ? cellRects(cells, range, cellM, lat, view, size) : []),
    [cells, range, cellM, lat, view, size],
  );
  const route = useMemo(() => (view && size ? routePaths(points, view, size) : []), [view, size, state.trackTick]);

  const pickedCell: HeatCell | null = picked ? cellAt(cells, picked.mx, picked.my, cellM, lat) : null;
  const pickedPx = pickedCell && view && size ? cellCentre(pickedCell, cellM, lat, view, size) : null;

  // Gestures: one finger pans, two fingers pinch-zoom (about the map centre:
  // touch locations inside nested views are relative to whichever tile was
  // hit), and a touch that barely moves is a tap that reads the cell under it.
  const gesture = useRef<{ start: MapView; dist: number | null; pinched: boolean } | null>(null);
  const origin = useRef<{ x: number; y: number } | null>(null);
  const viewRef = useRef(view);
  viewRef.current = view;
  const sizeRef = useRef(size);
  sizeRef.current = size;
  const responder = useMemo(
    () =>
      PanResponder.create({
        onStartShouldSetPanResponder: () => true,
        // Only claim a touch once it is clearly a drag or a pinch: claiming every
        // move stole taps from the zoom and GPS buttons (a finger always wobbles).
        onMoveShouldSetPanResponder: (e, g) =>
          e.nativeEvent.touches.length > 1 || Math.hypot(g.dx, g.dy) >= TAP_SLOP_PX,
        // The map sits in a ScrollView: keep the gesture once it is ours.
        onPanResponderTerminationRequest: () => false,
        onPanResponderGrant: (e) => {
          // Where the map box is on screen, for turning a tap's pageX/Y into map px.
          boxRef.current?.measure((_x, _y, _w, _h, pageX, pageY) => {
            origin.current = { x: pageX, y: pageY };
          });
          if (!viewRef.current) return;
          const d = touchDistance(e);
          gesture.current = { start: viewRef.current, dist: d, pinched: d !== null };
        },
        onPanResponderMove: (e, g) => {
          const st = gesture.current;
          const sz = sizeRef.current;
          if (!st || !sz) return;
          const d = touchDistance(e);
          if (d !== null) {
            if (st.dist === null) {
              // Second finger just landed: restart from here as a pinch.
              gesture.current = { start: viewRef.current ?? st.start, dist: d, pinched: true };
              return;
            }
            setFollowZoom(null);
            setManual(zoomAbout(st.start, Math.log2(d / st.dist), sz));
          } else if (st.dist === null && Math.hypot(g.dx, g.dy) >= TAP_SLOP_PX) {
            setFollowZoom(null);
            setManual(panBy(st.start, g.dx, g.dy));
          }
        },
        onPanResponderRelease: (e, g) => {
          const st = gesture.current;
          gesture.current = null;
          const v = viewRef.current;
          const sz = sizeRef.current;
          const o = origin.current;
          if (!st || st.pinched || !v || !sz || !o || Math.hypot(g.dx, g.dy) >= TAP_SLOP_PX) return;
          const x = e.nativeEvent.pageX - o.x;
          const y = e.nativeEvent.pageY - o.y;
          setPicked((prev) => (prev ? null : fromScreen(x, y, v, sz)));
        },
        onPanResponderTerminate: () => {
          gesture.current = null;
        },
      }),
    [],
  );

  const zoomBy = (dz: number) => {
    if (!view || !size) return;
    // Following you: zoom in place and keep following.
    if (following) setFollowZoom(clampZoom(view.zoom + dz));
    else setManual(zoomAbout(view, dz, size));
  };

  // GPS button: centre on you and follow you, at street level or closer.
  // With no fix yet it falls back to fitting the track.
  const centreOnMe = () => {
    setManual(null);
    setPicked(null);
    setFollowZoom(here ? Math.max(view?.zoom ?? SINGLE_POINT_ZOOM, SINGLE_POINT_ZOOM) : null);
  };

  const me = view && size && here ? toScreen(here, view, size) : null;
  const accPx = view && fix?.accuracyM ? (fix.accuracyM / metresPerUnit(fix.lat)) * worldPx(view.zoom) : 0;

  let empty: string | null = null;
  if (!view) {
    if (state.gpsStatus === 'denied') empty = 'Location permission is off. Turn it on to see the map.';
    else if (state.gpsStatus === 'error') empty = `GPS error: ${state.gpsDetail}`;
    else if (state.gpsStatus === 'off') empty = 'Connect or start recording to turn on GPS.';
    else empty = 'Waiting for a GPS fix…';
  }

  const tabs = (
    <SegmentedTabs
      theme={theme}
      items={MODES}
      value={mode}
      onChange={(m) => {
        onModeChange(m);
        setPicked(null);
      }}
    />
  );
  const legend = range ? (
    <ColourBar lo={fmtValue(range.lo, mode)} hi={fmtValue(range.hi, mode)} mode={mode} theme={theme} />
  ) : (
    <Text variant="legend" style={{ color: theme.textMuted }}>
      {points.length ? 'No sensor readings on this track yet.' : 'The heatmap appears once you record with a sensor connected.'}
    </Text>
  );
  // Full screen the buttons clear the status bar.
  const topInset = fullscreen ? insets.top + 8 : 8;

  const map = (
      <View
        ref={boxRef}
        onLayout={onLayout}
        style={
          fullscreen
            ? { flex: 1, overflow: 'hidden', backgroundColor: theme.surface2 }
            : { height, borderRadius: 16, overflow: 'hidden', backgroundColor: theme.surface2 }
        }
        {...responder.panHandlers}
      >
        {view && size && (
          <>
            <Tiles view={view} size={size} />
            <Svg width={size.width} height={size.height} style={{ position: 'absolute', left: 0, top: 0 }} pointerEvents="none">
              {/* The route, thin and white, under the cells, as plot_map.py draws it. */}
              {route.map((d, i) => (
                <Path key={`r${i}`} d={d} stroke="rgba(255,255,255,0.7)" strokeWidth={1.5} fill="none" strokeLinejoin="round" />
              ))}
              {rects.map((r, i) => (
                <Rect key={`c${i}`} x={r.x} y={r.y} width={r.size} height={r.size} fill={r.fill} opacity={CELL_OPACITY} />
              ))}
              {pickedPx && (
                <Rect
                  x={pickedPx.x - pickedPx.size / 2 - 2}
                  y={pickedPx.y - pickedPx.size / 2 - 2}
                  width={pickedPx.size + 4}
                  height={pickedPx.size + 4}
                  fill="none"
                  stroke="#ffffff"
                  strokeWidth={2.5}
                />
              )}
              {me && (
                <>
                  {accPx > 9 && <Circle cx={me.x} cy={me.y} r={accPx} fill="rgba(53,131,221,0.18)" stroke="rgba(53,131,221,0.6)" strokeWidth={1} />}
                  <Circle cx={me.x} cy={me.y} r={8} fill="#3583dd" stroke="#ffffff" strokeWidth={3} />
                </>
              )}
            </Svg>
          </>
        )}
        {pickedCell && pickedPx && size && (
          <Tooltip cell={pickedCell} mode={mode} at={pickedPx} size={size} cellM={cellM} theme={theme} />
        )}
        {empty && (
          <Box flex={1} alignItems="center" justifyContent="center" padding="l">
            <Text variant="rowMeta" style={{ textAlign: 'center' }}>
              {empty}
            </Text>
          </Box>
        )}
        {view && (
          <View style={{ position: 'absolute', right: 8, top: topInset, gap: 8 }}>
            {onToggleFullscreen && (
              <MapButton
                icon={fullscreen ? 'fullscreen-exit' : 'fullscreen'}
                label={fullscreen ? 'Exit full screen' : 'Full screen'}
                onPress={onToggleFullscreen}
                theme={theme}
              />
            )}
            <MapButton icon="plus" label="Zoom in" onPress={() => zoomBy(1)} theme={theme} />
            <MapButton icon="minus" label="Zoom out" onPress={() => zoomBy(-1)} theme={theme} />
            <MapButton
              icon={following ? 'crosshairs-gps' : 'crosshairs'}
              label="Centre on my position"
              onPress={centreOnMe}
              theme={theme}
              active={following}
            />
          </View>
        )}
        {view && (
          <View
            pointerEvents="none"
            style={{
              position: 'absolute',
              left: 0,
              bottom: 0,
              paddingHorizontal: 6,
              paddingVertical: 2,
              backgroundColor: 'rgba(0,0,0,0.5)',
              borderTopRightRadius: 6,
            }}
          >
            <Text style={{ color: '#ffffff', fontSize: 9 }}>{ESRI_ATTRIBUTION}</Text>
          </View>
        )}
      </View>
  );

  if (fullscreen) {
    return (
      <View style={{ flex: 1, backgroundColor: theme.bg }}>
        {map}
        <Box gap="s" paddingHorizontal="l" paddingTop="m" style={{ paddingBottom: spacing.m + insets.bottom }}>
          {tabs}
          {legend}
        </Box>
      </View>
    );
  }
  return (
    <Box gap="s">
      {tabs}
      {map}
      {legend}
    </Box>
  );
}

function cellCentre(c: HeatCell, cellM: number, lat: number, view: MapView, size: Size): { x: number; y: number; size: number } {
  const cell = cellM / metresPerUnit(lat);
  const s = toScreen({ mx: (c.ix + 0.5) * cell, my: (c.iy + 0.5) * cell }, view, size);
  return { ...s, size: cell * worldPx(view.zoom) };
}

const TIP_W = 170;
/** Closest the value pop-up comes to the map's sides. */
const TIP_MARGIN = 6;

/** The tapped cell's value, in a callout above it (below if near the top). */
function Tooltip({
  cell,
  mode,
  at,
  size,
  cellM,
  theme,
}: {
  cell: HeatCell;
  mode: HeatMode;
  at: { x: number; y: number; size: number };
  size: Size;
  cellM: number;
  theme: Theme;
}) {
  const left = Math.max(TIP_MARGIN, Math.min(size.width - TIP_W - TIP_MARGIN, at.x - TIP_W / 2));
  const above = at.y - at.size / 2 > 80;
  const pos = above ? { bottom: size.height - (at.y - at.size / 2) + 8 } : { top: at.y + at.size / 2 + 8 };
  const how = mode === 'raw' ? 'mean' : 'steepest';
  return (
    <View
      pointerEvents="none"
      style={{
        position: 'absolute',
        left,
        width: TIP_W,
        ...pos,
        paddingHorizontal: 10,
        paddingVertical: 6,
        borderRadius: 10,
        backgroundColor: theme.surface,
        borderWidth: 1,
        borderColor: theme.border,
      }}
    >
      <Text variant="rowTitle">{fmtValue(cell.value, mode)}</Text>
      <Text variant="legend" style={{ color: theme.textMuted }}>
        {`${how} of ${cell.n} fix${cell.n === 1 ? '' : 'es'} · ${cellM} m cell`}
      </Text>
    </View>
  );
}
