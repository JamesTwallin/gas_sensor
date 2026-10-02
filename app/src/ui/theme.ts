// Colour tokens. Outdoor instrument: dark by default, high contrast, big touch
// targets; a light theme for bright sun. Pure data, so it can be imported from
// tests too.
//
// The two series hues were validated against the card surfaces with the dataviz
// palette checker (lightness band, chroma, CVD separation, contrast), so keep
// them paired: CH4 blue, LPG orange.

export interface Theme {
  bg: string;
  surface: string;
  surface2: string;
  text: string;
  textMuted: string;
  textFaint: string;
  border: string;
  grid: string;
  axis: string;
  ch4: string;
  lpg: string;
  /** First-derivative trace on the live charts. */
  slope: string;
  good: string;
  warning: string;
  critical: string;
  info: string;
  /** Primary action colour (Connect). */
  accent: string;
  /** Text drawn on a `good` / `critical` / `accent` fill. */
  onDark: string;
  /** Text drawn on a `warning` fill. */
  onLight: string;
}

export const DARK: Theme = {
  bg: '#0f1114',
  surface: '#171a1f',
  surface2: '#1f232a',
  text: '#f2f3f5',
  textMuted: '#9aa1ad',
  textFaint: '#5f6673',
  border: '#2a2f38',
  grid: '#252a32',
  axis: '#3a404a',
  ch4: '#3583dd',
  lpg: '#d4762a',
  slope: '#1fbf85',
  good: '#2fa363',
  warning: '#e6a11b',
  critical: '#d9453d',
  info: '#3583dd',
  accent: '#3583dd',
  onDark: '#ffffff',
  onLight: '#101114',
};

export const LIGHT: Theme = {
  ...DARK,
  bg: '#f6f7f9',
  surface: '#ffffff',
  surface2: '#eceef2',
  text: '#111318',
  textMuted: '#5b6271',
  textFaint: '#8a919e',
  border: '#d6dae2',
  grid: '#e6e9ee',
  axis: '#c2c7d0',
  ch4: '#2a6fc4',
  lpg: '#b8621f',
  slope: '#0f9a6a',
  good: '#1f8f52',
  warning: '#c98a0e',
  critical: '#c73a33',
  info: '#2a6fc4',
  accent: '#2a6fc4',
};

export const themeFor = (light: boolean): Theme => (light ? LIGHT : DARK);

/** Font family names as registered by @expo-google-fonts/inter. */
export const FONT = {
  regular: 'Inter_400Regular',
  medium: 'Inter_500Medium',
  semibold: 'Inter_600SemiBold',
  bold: 'Inter_700Bold',
  extrabold: 'Inter_800ExtraBold',
} as const;

/** Minimum touch target. */
export const TAP = 48;

export type Severity = 'critical' | 'warning' | 'info';
