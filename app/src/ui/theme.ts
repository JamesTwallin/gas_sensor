// Colour tokens, ported from the rev B web app's styles.css. Outdoor instrument:
// dark by default, high contrast, big touch targets; a light theme for bright sun.
// Pure data, so it can be imported from tests too.

export interface Theme {
  bg: string;
  surface: string;
  surface2: string;
  text: string;
  textMuted: string;
  border: string;
  grid: string;
  axis: string;
  ch4: string;
  lpg: string;
  baseline: string;
  good: string;
  warning: string;
  critical: string;
  info: string;
  /** Text drawn on a `good` / `critical` fill. */
  onDark: string;
  /** Text drawn on a `warning` fill. */
  onLight: string;
}

export const DARK: Theme = {
  bg: '#111110',
  surface: '#1a1a19',
  surface2: '#262624',
  text: '#f7f7f5',
  textMuted: '#b5b5ae',
  border: '#3a3a37',
  grid: '#4a4a46',
  axis: '#77776f',
  ch4: '#3987e5',
  lpg: '#d95926',
  baseline: '#f7f7f5',
  good: '#0ca30c',
  warning: '#fab219',
  critical: '#d03b3b',
  info: '#3987e5',
  onDark: '#ffffff',
  onLight: '#111111',
};

export const LIGHT: Theme = {
  ...DARK,
  bg: '#ffffff',
  surface: '#f4f4f1',
  surface2: '#e6e6e1',
  text: '#0b0b0a',
  textMuted: '#4a4a45',
  border: '#b9b9b2',
  grid: '#b9b9b2',
  axis: '#6d6d66',
  ch4: '#2a78d6',
  lpg: '#c4501f',
  baseline: '#0b0b0a',
};

export const themeFor = (light: boolean): Theme => (light ? LIGHT : DARK);

/** Minimum touch target, the `--tap` custom property. */
export const TAP = 56;

export type Severity = 'critical' | 'warning' | 'info';
