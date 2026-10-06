// Slippy-map geometry for the survey map (ui/SurveyMap.tsx): Web Mercator
// projection, which tiles cover the screen, and the zoom that fits a track.
// Pure and DOM-free so it is unit-tested; the view only positions Images and
// SVG paths with the numbers it returns.
//
// Positions are kept as normalised Mercator coordinates (mx, my in 0..1, x
// east, y south), the same space every tile zoom level subdivides. A view is a
// centre in that space plus a fractional zoom; at zoom z the whole world is
// TILE_PX * 2^z screen pixels wide.

export const TILE_PX = 256;
/** Deepest tile level requested. Esri World Imagery serves 19 nearly everywhere. */
export const MAX_TILE_ZOOM = 19;
/** Furthest the user can zoom in: tiles at MAX_TILE_ZOOM are scaled beyond it. */
export const MAX_ZOOM = 21;
export const MIN_ZOOM = 2;
/** Zoom used when there is a single point to show (a street or two across). */
export const SINGLE_POINT_ZOOM = 17;
/** Auto-fit never zooms in past this, so a short track still shows its surroundings. */
export const MAX_FIT_ZOOM = 18;
const MAX_LAT = 85.05112878;

export interface Merc {
  mx: number;
  my: number;
}

export interface MapView {
  /** Centre, normalised Mercator. */
  cx: number;
  cy: number;
  zoom: number;
}

export interface Size {
  width: number;
  height: number;
}

export function lonLatToMerc(lon: number, lat: number): Merc {
  const la = (Math.max(-MAX_LAT, Math.min(MAX_LAT, lat)) * Math.PI) / 180;
  return {
    mx: (lon + 180) / 360,
    my: (1 - Math.log(Math.tan(la) + 1 / Math.cos(la)) / Math.PI) / 2,
  };
}

export function clampZoom(z: number): number {
  return Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, z));
}

/** Screen pixels per unit of normalised Mercator at this zoom. */
export function worldPx(zoom: number): number {
  return TILE_PX * Math.pow(2, zoom);
}

/** Normalised Mercator point -> screen px inside a view of `size`. */
export function toScreen(p: Merc, view: MapView, size: Size): { x: number; y: number } {
  const w = worldPx(view.zoom);
  return {
    x: (p.mx - view.cx) * w + size.width / 2,
    y: (p.my - view.cy) * w + size.height / 2,
  };
}

/** Screen px inside a view of `size` -> normalised Mercator (the inverse of toScreen). */
export function fromScreen(x: number, y: number, view: MapView, size: Size): Merc {
  const w = worldPx(view.zoom);
  return { mx: view.cx + (x - size.width / 2) / w, my: view.cy + (y - size.height / 2) / w };
}

/** Move the view by a screen-pixel drag (finger moved dx, dy: the map follows it). */
export function panBy(view: MapView, dx: number, dy: number): MapView {
  const w = worldPx(view.zoom);
  return {
    ...view,
    cx: view.cx - dx / w,
    cy: Math.max(0, Math.min(1, view.cy - dy / w)),
  };
}

/**
 * Zoom by `dz` levels keeping the map point under screen pixel (fx, fy) still,
 * as a pinch or a double tap expects. Defaults to the centre.
 */
export function zoomAbout(view: MapView, dz: number, size: Size, fx = size.width / 2, fy = size.height / 2): MapView {
  const zoom = clampZoom(view.zoom + dz);
  const w0 = worldPx(view.zoom);
  const w1 = worldPx(zoom);
  // Map point under the focus, before and after, must coincide.
  const px = view.cx + (fx - size.width / 2) / w0;
  const py = view.cy + (fy - size.height / 2) / w0;
  return {
    zoom,
    cx: px - (fx - size.width / 2) / w1,
    cy: Math.max(0, Math.min(1, py - (fy - size.height / 2) / w1)),
  };
}

/**
 * The view that fits every point inside `size` with `padPx` clear on each side.
 * One point (or several on top of each other) gets SINGLE_POINT_ZOOM.
 */
export function fitView(points: readonly Merc[], size: Size, padPx: number): MapView | null {
  if (!points.length) return null;
  let x0 = Infinity;
  let x1 = -Infinity;
  let y0 = Infinity;
  let y1 = -Infinity;
  for (const p of points) {
    if (p.mx < x0) x0 = p.mx;
    if (p.mx > x1) x1 = p.mx;
    if (p.my < y0) y0 = p.my;
    if (p.my > y1) y1 = p.my;
  }
  const cx = (x0 + x1) / 2;
  const cy = (y0 + y1) / 2;
  const availW = Math.max(1, size.width - 2 * padPx);
  const availH = Math.max(1, size.height - 2 * padPx);
  const dx = x1 - x0;
  const dy = y1 - y0;
  let zoom = SINGLE_POINT_ZOOM;
  if (dx > 0 || dy > 0) {
    const zx = dx > 0 ? Math.log2(availW / (dx * TILE_PX)) : Infinity;
    const zy = dy > 0 ? Math.log2(availH / (dy * TILE_PX)) : Infinity;
    zoom = Math.min(zx, zy, MAX_FIT_ZOOM);
  }
  return { cx, cy, zoom: clampZoom(zoom) };
}

export interface TilePlacement {
  /** Stable key, also the cache identity: z/x/y with x wrapped. */
  key: string;
  z: number;
  x: number;
  y: number;
  left: number;
  top: number;
  size: number;
}

/** The tiles that cover the view, with where each one goes on screen. */
export function visibleTiles(view: MapView, size: Size): TilePlacement[] {
  const z = Math.max(0, Math.min(MAX_TILE_ZOOM, Math.floor(view.zoom)));
  const n = Math.pow(2, z);
  const tilePx = worldPx(view.zoom) / n; // on-screen size of one tile at level z
  // Screen origin (top-left) in tile units at level z.
  const ox = view.cx * n - size.width / 2 / tilePx;
  const oy = view.cy * n - size.height / 2 / tilePx;
  const tx0 = Math.floor(ox);
  const ty0 = Math.max(0, Math.floor(oy));
  const tx1 = Math.floor(ox + size.width / tilePx);
  const ty1 = Math.min(n - 1, Math.floor(oy + size.height / tilePx));
  const out: TilePlacement[] = [];
  for (let ty = ty0; ty <= ty1; ty++) {
    for (let tx = tx0; tx <= tx1; tx++) {
      const x = ((tx % n) + n) % n;
      out.push({
        key: `${z}/${x}/${ty}/${tx}`,
        z,
        x,
        y: ty,
        left: (tx - ox) * tilePx,
        top: (ty - oy) * tilePx,
        size: tilePx,
      });
    }
  }
  return out;
}

/** Esri World Imagery, the satellite basemap tools/plot_map.py uses. */
export function esriImageryUrl(t: { z: number; x: number; y: number }): string {
  return `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/${t.z}/${t.y}/${t.x}`;
}

export const ESRI_ATTRIBUTION = 'Powered by Esri · Esri, Maxar, Earthstar Geographics';
