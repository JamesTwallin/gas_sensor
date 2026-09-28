// Layout system: Shopify Restyle over the palette in theme.ts.
//
// Every margin, padding and gap in the UI is one of the `spacing` steps below,
// referenced by name (`padding="m"`), so components cannot drift apart by a few
// pixels. Text styles are named variants (one type scale, one family: Inter).
// theme.ts stays the source of colours; the SVG charts paint from it directly.

import { createBox, createText, createTheme, ThemeProvider, useTheme as useRestyleTheme } from '@shopify/restyle';
import { DARK, FONT, LIGHT, type Theme as Palette } from './theme';

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
  xl: 20,
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
      defaults: { color: 'text', fontSize: 16, fontFamily: FONT.regular },
      h2: { color: 'text', fontSize: 24, fontFamily: FONT.bold, letterSpacing: -0.3 },
      h3: { color: 'text', fontSize: 18, fontFamily: FONT.semibold },
      body: { color: 'text', fontSize: 16, fontFamily: FONT.regular },
      hint: { color: 'textMuted', fontSize: 14, lineHeight: 20, fontFamily: FONT.regular },
      eyebrow: { color: 'textMuted', fontSize: 11, letterSpacing: 1.2, fontFamily: FONT.semibold, textTransform: 'uppercase' },
      label: { color: 'text', fontSize: 16, fontFamily: FONT.semibold },
      labelHint: { color: 'textMuted', fontSize: 13, lineHeight: 18, fontFamily: FONT.regular },
      chip: { color: 'textMuted', fontSize: 14, fontFamily: FONT.semibold },
      link: { color: 'text', fontSize: 15, fontFamily: FONT.semibold },
      button: { color: 'text', fontSize: 16, fontFamily: FONT.semibold },
      buttonBig: { color: 'text', fontSize: 17, fontFamily: FONT.bold },
      strip: { color: 'textMuted', fontSize: 14, fontFamily: FONT.medium },
      stripStrong: { color: 'text', fontSize: 14, fontFamily: FONT.semibold },
      stateWord: { color: 'text', fontFamily: FONT.extrabold, letterSpacing: -1.5 },
      stateSub: { color: 'text', fontSize: 22, fontFamily: FONT.semibold },
      stateLine: { color: 'text', fontSize: 16, fontFamily: FONT.medium },
      cardTitle: { color: 'text', fontSize: 14, fontFamily: FONT.semibold },
      cardValue: { color: 'text', fontSize: 18, fontFamily: FONT.semibold, fontVariant: ['tabular-nums'] },
      tileKey: { color: 'textMuted', fontSize: 12, fontFamily: FONT.medium },
      tileValue: { color: 'text', fontSize: 20, fontFamily: FONT.semibold },
      tileUnit: { color: 'textMuted', fontSize: 13, fontFamily: FONT.medium },
      legend: { color: 'textMuted', fontSize: 13, fontFamily: FONT.medium },
      rowTitle: { color: 'text', fontSize: 16, fontFamily: FONT.semibold },
      rowMeta: { color: 'textMuted', fontSize: 13, fontFamily: FONT.regular },
      toast: { color: 'bg', fontSize: 15, fontFamily: FONT.semibold },
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
