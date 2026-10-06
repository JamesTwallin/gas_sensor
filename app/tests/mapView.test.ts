import { describe, expect, it } from 'vitest';
import {
  MAX_FIT_ZOOM,
  MAX_TILE_ZOOM,
  MIN_ZOOM,
  SINGLE_POINT_ZOOM,
  TILE_PX,
  esriImageryUrl,
  fitView,
  lonLatToMerc,
  panBy,
  toScreen,
  visibleTiles,
  worldPx,
  zoomAbout,
} from '../src/core/mapView';

const SIZE = { width: 400, height: 300 };

describe('lonLatToMerc', () => {
  it('puts 0,0 in the middle of the world', () => {
    const m = lonLatToMerc(0, 0);
    expect(m.mx).toBeCloseTo(0.5, 12);
    expect(m.my).toBeCloseTo(0.5, 12);
  });

  it('runs west to east and north to south', () => {
    const london = lonLatToMerc(-0.1276, 51.5072);
    expect(london.mx).toBeLessThan(0.5);
    expect(london.my).toBeLessThan(0.5);
    expect(lonLatToMerc(-180, 0).mx).toBe(0);
    expect(lonLatToMerc(180, 0).mx).toBe(1);
  });

  it('matches the standard tile numbering', () => {
    // London at zoom 10 is tile x=511, y=340 (OSM slippy-map formula).
    const m = lonLatToMerc(-0.1276, 51.5072);
    expect(Math.floor(m.mx * 1024)).toBe(511);
    expect(Math.floor(m.my * 1024)).toBe(340);
  });

  it('clamps the poles instead of returning infinity', () => {
    expect(Number.isFinite(lonLatToMerc(0, 90).my)).toBe(true);
    expect(lonLatToMerc(0, 90).my).toBeCloseTo(0, 6);
  });
});

describe('toScreen / panBy / zoomAbout', () => {
  const view = { cx: 0.5, cy: 0.5, zoom: 10 };

  it('draws the centre in the middle of the view', () => {
    expect(toScreen({ mx: 0.5, my: 0.5 }, view, SIZE)).toEqual({ x: 200, y: 150 });
  });

  it('pans so the map follows the finger', () => {
    const p = { mx: 0.5, my: 0.5 };
    const moved = panBy(view, 30, -20);
    const s = toScreen(p, moved, SIZE);
    expect(s.x).toBeCloseTo(230, 9);
    expect(s.y).toBeCloseTo(130, 9);
  });

  it('keeps the point under the fingers still while zooming', () => {
    const focus = { x: 320, y: 60 };
    const w = worldPx(view.zoom);
    const under = { mx: view.cx + (focus.x - 200) / w, my: view.cy + (focus.y - 150) / w };
    const z = zoomAbout(view, 1.5, SIZE, focus.x, focus.y);
    expect(z.zoom).toBe(11.5);
    const s = toScreen(under, z, SIZE);
    expect(s.x).toBeCloseTo(focus.x, 6);
    expect(s.y).toBeCloseTo(focus.y, 6);
  });

  it('clamps zoom', () => {
    expect(zoomAbout(view, -100, SIZE).zoom).toBe(MIN_ZOOM);
  });
});

describe('fitView', () => {
  it('returns null with nothing to show', () => {
    expect(fitView([], SIZE, 20)).toBeNull();
  });

  it('centres a single point at the single-point zoom', () => {
    const p = lonLatToMerc(-1.25, 51.75);
    expect(fitView([p], SIZE, 20)).toEqual({ cx: p.mx, cy: p.my, zoom: SINGLE_POINT_ZOOM });
  });

  it('fits a track inside the padding', () => {
    const pts = [lonLatToMerc(-1.26, 51.75), lonLatToMerc(-1.24, 51.76), lonLatToMerc(-1.25, 51.745)];
    const v = fitView(pts, SIZE, 20)!;
    for (const p of pts) {
      const s = toScreen(p, v, SIZE);
      expect(s.x).toBeGreaterThanOrEqual(20 - 1e-6);
      expect(s.x).toBeLessThanOrEqual(380 + 1e-6);
      expect(s.y).toBeGreaterThanOrEqual(20 - 1e-6);
      expect(s.y).toBeLessThanOrEqual(280 + 1e-6);
    }
  });

  it('does not zoom in past MAX_FIT_ZOOM on a short track', () => {
    const a = lonLatToMerc(-1.25, 51.75);
    const b = lonLatToMerc(-1.25001, 51.75001);
    expect(fitView([a, b], SIZE, 20)!.zoom).toBe(MAX_FIT_ZOOM);
  });
});

describe('visibleTiles', () => {
  it('covers the whole view with no gaps', () => {
    const view = { cx: 0.4987, cy: 0.3321, zoom: 15.4 };
    const tiles = visibleTiles(view, SIZE);
    expect(tiles.every((t) => t.z === 15)).toBe(true);
    const size = tiles[0].size;
    expect(size).toBeCloseTo(TILE_PX * Math.pow(2, 0.4), 9);
    // Every corner and the centre of the view lands inside some tile.
    for (const [x, y] of [
      [0, 0],
      [399.9, 0],
      [0, 299.9],
      [399.9, 299.9],
      [200, 150],
    ]) {
      expect(tiles.some((t) => x >= t.left && x < t.left + t.size && y >= t.top && y < t.top + t.size)).toBe(true);
    }
  });

  it('puts the tile containing the centre under the centre', () => {
    const view = { cx: 0.4987, cy: 0.3321, zoom: 12 };
    const n = 4096;
    const tx = Math.floor(view.cx * n);
    const ty = Math.floor(view.cy * n);
    const t = visibleTiles(view, SIZE).find((v) => v.x === tx && v.y === ty)!;
    expect(t.left).toBeLessThanOrEqual(200);
    expect(t.left + t.size).toBeGreaterThan(200);
    expect(t.top).toBeLessThanOrEqual(150);
    expect(t.top + t.size).toBeGreaterThan(150);
  });

  it('scales the deepest tiles up rather than asking for levels that do not exist', () => {
    const tiles = visibleTiles({ cx: 0.5, cy: 0.5, zoom: 20.5 }, SIZE);
    expect(tiles.every((t) => t.z === MAX_TILE_ZOOM)).toBe(true);
    expect(tiles[0].size).toBeCloseTo(TILE_PX * Math.pow(2, 1.5), 9);
  });

  it('wraps x across the antimeridian and never asks for rows off the world', () => {
    const tiles = visibleTiles({ cx: 0.0001, cy: 0.0001, zoom: 3 }, SIZE);
    for (const t of tiles) {
      expect(t.x).toBeGreaterThanOrEqual(0);
      expect(t.x).toBeLessThan(8);
      expect(t.y).toBeGreaterThanOrEqual(0);
    }
    expect(new Set(tiles.map((t) => t.key)).size).toBe(tiles.length);
  });
});

describe('esriImageryUrl', () => {
  it('uses the z/y/x order Esri expects', () => {
    expect(esriImageryUrl({ z: 17, x: 65000, y: 43000 })).toBe(
      'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/17/43000/65000',
    );
  });
});
