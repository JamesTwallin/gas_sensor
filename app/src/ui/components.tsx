// Shared bits of chrome: pills, banners, buttons, section headings, toast.
// Layout and type come from ui/restyle.ts (spacing steps, text variants);
// the `theme` prop is the colour palette, kept for callers that also paint SVG.

import { useEffect } from 'react';
import { Pressable, type StyleProp, type ViewStyle } from 'react-native';
import type { LinkStatus } from '../services/device';
import { Box, Text, borderRadii, sizes, spacing, useTheme } from './restyle';
import type { Severity, Theme } from './theme';

export function Pill({
  theme,
  children,
  status,
  ghost,
  onPress,
  tint,
  flex,
}: {
  theme: Theme;
  children: React.ReactNode;
  status?: LinkStatus;
  ghost?: boolean;
  onPress?: () => void;
  tint?: string;
  /** Let this pill take the slack in a row (its text is ellipsised, the others never wrap). */
  flex?: number;
}) {
  const dotColour =
    status === 'connected'
      ? theme.good
      : status === 'connecting' || status === 'reconnecting'
        ? theme.warning
        : status === 'error'
          ? theme.critical
          : theme.textMuted;
  const body = (
    <Box
      flexDirection="row"
      alignItems="center"
      gap="s"
      minHeight={36}
      paddingHorizontal="m"
      paddingVertical="xs"
      borderRadius="pill"
      borderWidth={2}
      flexShrink={1}
      style={{ borderColor: tint ?? theme.border, backgroundColor: ghost ? 'transparent' : theme.surface }}
    >
      {status !== undefined && <Box width={12} height={12} borderRadius="pill" style={{ backgroundColor: dotColour }} />}
      <Text variant="pill" numberOfLines={1} flexShrink={1} style={tint ? { color: tint } : undefined}>
        {children}
      </Text>
    </Box>
  );
  const wrapped = onPress ? <Pressable onPress={onPress}>{body}</Pressable> : body;
  return flex !== undefined ? <Box flex={flex}>{wrapped}</Box> : wrapped;
}

/** One line, fixed height: it lives in the status strip, which never changes size. */
export function Banner({
  theme,
  severity,
  text,
  tint,
}: {
  theme: Theme;
  severity: Severity;
  text: string;
  /** Border/text colour override (the recording indicator). */
  tint?: string;
}) {
  const look =
    severity === 'critical'
      ? { bg: theme.critical, border: theme.critical, variant: 'bannerCritical' as const }
      : severity === 'warning'
        ? { bg: 'transparent', border: theme.warning, variant: 'bannerWarning' as const }
        : { bg: 'transparent', border: theme.border, variant: 'bannerInfo' as const };
  return (
    <Box
      height={36}
      justifyContent="center"
      paddingHorizontal="m"
      borderRadius="s"
      borderWidth={2}
      style={{ backgroundColor: look.bg, borderColor: tint ?? look.border }}
    >
      <Text variant={look.variant} numberOfLines={1} style={tint ? { color: tint } : undefined}>
        {text}
      </Text>
    </Box>
  );
}

export function Btn({
  theme,
  title,
  onPress,
  disabled,
  big,
  variant = 'default',
  style,
}: {
  theme: Theme;
  title: string;
  onPress: () => void;
  disabled?: boolean;
  big?: boolean;
  variant?: 'default' | 'record' | 'recording' | 'danger' | 'primary';
  style?: StyleProp<ViewStyle>;
}) {
  const skin =
    variant === 'record'
      ? { bg: theme.critical, border: theme.critical, fg: theme.onDark }
      : variant === 'recording'
        ? { bg: theme.text, border: theme.text, fg: theme.bg }
        : variant === 'danger'
          ? { bg: theme.surface2, border: theme.critical, fg: theme.text }
          : variant === 'primary'
            ? { bg: theme.text, border: theme.text, fg: theme.bg }
            : { bg: theme.surface2, border: theme.border, fg: theme.text };
  return (
    <Pressable
      accessibilityRole="button"
      onPress={onPress}
      disabled={disabled}
      style={({ pressed }) => [
        {
          minHeight: big ? sizes.tapBig : sizes.tap,
          paddingHorizontal: big ? spacing.s : spacing.l,
          paddingVertical: spacing.s,
          borderRadius: borderRadii.m,
          borderWidth: 2,
          alignItems: 'center',
          justifyContent: 'center',
          backgroundColor: skin.bg,
          borderColor: skin.border,
          opacity: disabled ? 0.45 : pressed ? 0.85 : 1,
        },
        style,
      ]}
    >
      <Text variant={big ? 'buttonBig' : 'button'} numberOfLines={1} style={{ color: skin.fg }}>
        {title}
      </Text>
    </Pressable>
  );
}

export function Hint({ children }: { theme?: Theme; children: React.ReactNode }) {
  return (
    <Text variant="hint" marginVertical="xs">
      {children}
    </Text>
  );
}

export function H2({ children }: { theme?: Theme; children: React.ReactNode }) {
  return (
    <Text variant="h2" marginTop="s" marginBottom="s">
      {children}
    </Text>
  );
}

export function H3({ children }: { theme?: Theme; children: React.ReactNode }) {
  return (
    <Text variant="h3" marginTop="l" marginBottom="xs">
      {children}
    </Text>
  );
}

export function Toast({
  theme,
  text,
  id,
  onDone,
}: {
  theme: Theme;
  text: string;
  id: number;
  onDone: (id: number) => void;
}) {
  useEffect(() => {
    const t = setTimeout(() => onDone(id), 3500);
    return () => clearTimeout(t);
  }, [id, onDone]);
  return (
    <Box pointerEvents="none" position="absolute" left={0} right={0} bottom={spacing.xl} alignItems="center">
      <Box
        paddingHorizontal="l"
        paddingVertical="m"
        borderRadius="m"
        maxWidth="90%"
        style={{ backgroundColor: theme.text }}
      >
        <Text variant="toast">{text}</Text>
      </Box>
    </Box>
  );
}

/** The legend strip above a chart. */
export function Legend({ items, note }: { theme?: Theme; items: [string, string][]; note: string }) {
  return (
    <Box flexDirection="row" alignItems="center" gap="m" paddingBottom="xs">
      {items.map(([label, colour]) => (
        <Box key={label} flexDirection="row" alignItems="center" gap="xs">
          <Box width={12} height={12} borderRadius="xs" style={{ backgroundColor: colour }} />
          <Text variant="legend">{label}</Text>
        </Box>
      ))}
      <Text variant="legend" style={{ marginLeft: 'auto', fontWeight: '400' }}>
        {note}
      </Text>
    </Box>
  );
}

/** Where a plain RN style object needs the same steps as Box (inputs, pressables). */
export function useSpacing() {
  return useTheme().spacing;
}
