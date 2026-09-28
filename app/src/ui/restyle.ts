// Layout system: Shopify Restyle over the colour palette in theme.ts.
//
// Every margin, padding and gap in the UI is one of the `spacing` steps below,
// referenced by name (`padding="m"`), so components cannot drift apart by a few
// pixels. Text styles are named variants for the same reason. The palette is
// unchanged; theme.ts stays the source of colours (the SVG charts paint from it
// directly).

import { createBox, createText, createTheme, ThemeProvider, useTheme as useRestyleTheme } from '@shopify/restyle';
import { DARK, LIGHT, type Theme as Palette } from './theme';

/** The spacing scale (px). `s` separates siblings, `m` pads cards, `l` pads screens. */
export const spacing = {
  none: 0,
  xxs: 2,
  xs: 4,
  s: 8,
  m: 12,
  l: 16,
  xl: 24,
  xxl: 32,
} as const;

export const borderRadii = {
  xs: 4,
  s: 8,
  m: 12,
  l: 16,
  pill: 999,
} as const;

/** Touch-target heights: `tap` is the minimum for gloved fingers, `tapBig` for the action dock. */
export const sizes = {
  tap: 48,
  tapBig: 56,
  input: 48,
} as const;

function makeTheme(p: Palette) {
  return createTheme({
    colors: { ...p, transparent: 'transparent' },
    spacing,
    borderRadii,
    breakpoints: { phone: 0, tablet: 720 },
    textVariants: {
      defaults: { color: 'text', fontSize: 17 },
      h2: { color: 'text', fontSize: 26, fontWeight: '700' },
      h3: { color: 'text', fontSize: 20, fontWeight: '700' },
      body: { color: 'text', fontSize: 17 },
      hint: { color: 'textMuted', fontSize: 15, lineHeight: 20 },
      label: { color: 'text', fontSize: 17, fontWeight: '600' },
      labelHint: { color: 'textMuted', fontSize: 14, lineHeight: 18 },
      pill: { color: 'text', fontSize: 15, fontWeight: '600' },
      button: { color: 'text', fontSize: 17, fontWeight: '700' },
      buttonBig: { color: 'text', fontSize: 18, fontWeight: '700' },
      bannerCritical: { color: 'onDark', fontSize: 17, fontWeight: '700' },
      bannerWarning: { color: 'text', fontSize: 17, fontWeight: '700' },
      bannerInfo: { color: 'textMuted', fontSize: 15, fontWeight: '600' },
      stateWord: { color: 'text', fontWeight: '900', letterSpacing: -1 },
      stateSub: { color: 'text', fontSize: 24, fontWeight: '700', fontVariant: ['tabular-nums'] },
      stateLine: { color: 'text', fontSize: 18, fontWeight: '600' },
      cellKey: { color: 'textMuted', fontSize: 13, fontWeight: '600' },
      cellValue: { color: 'text', fontSize: 18, fontWeight: '700', fontVariant: ['tabular-nums'] },
      legend: { color: 'textMuted', fontSize: 14, fontWeight: '600' },
      rowTitle: { color: 'text', fontSize: 17, fontWeight: '700' },
      rowMeta: { color: 'textMuted', fontSize: 14 },
      toast: { color: 'bg', fontSize: 17, fontWeight: '700' },
    },
  });
}

export const darkTheme = makeTheme(DARK);
export const lightTheme: typeof darkTheme = makeTheme(LIGHT);
export type AppTheme = typeof darkTheme;

export const Box = createBox<AppTheme>();
export const Text = createText<AppTheme>();
export const useTheme = () => useRestyleTheme<AppTheme>();
export { ThemeProvider };
