// Shared chrome: status chips, the status strip, buttons, segmented tabs,
// cards, headings, toast. Layout and type come from ui/restyle.ts; the `theme`
// prop is the colour palette (callers that also paint SVG already hold it).

import { MaterialCommunityIcons } from '@expo/vector-icons';
import { useEffect, useRef, type ComponentProps } from 'react';
import { Pressable, type StyleProp, type ViewStyle } from 'react-native';
import type { LinkStatus } from '../services/device';
import { Box, Text, borderRadii, sizes, spacing } from './restyle';
import type { Severity, Theme } from './theme';

export type IconName = ComponentProps<typeof MaterialCommunityIcons>['name'];

export function Icon({ name, size = 16, color }: { name: IconName; size?: number; color: string }) {
  return <MaterialCommunityIcons name={name} size={size} color={color} />;
}

/** The link chip: status dot + device name; takes the slack in the header row. */
export function LinkChip({
  theme,
  status,
  label,
  onPress,
}: {
  theme: Theme;
  status: LinkStatus;
  label: string;
  onPress?: () => void;
}) {
  const dot =
    status === 'connected'
      ? theme.good
      : status === 'connecting' || status === 'reconnecting'
        ? theme.warning
        : status === 'error'
          ? theme.critical
          : theme.textFaint;
  return (
    <Pressable onPress={onPress} style={{ flex: 1 }}>
      <Box
        flexDirection="row"
        alignItems="center"
        gap="s"
        height={40}
        paddingHorizontal="m"
        borderRadius="pill"
        style={{ backgroundColor: theme.surface }}
      >
        <Box width={10} height={10} borderRadius="pill" style={{ backgroundColor: dot }} />
        <Text variant="link" numberOfLines={1} flexShrink={1}>
          {label}
        </Text>
      </Box>
    </Pressable>
  );
}

/** A small icon + text chip for battery / GPS: never wraps, never grows. */
export function MetaChip({ theme, icon, text, tint }: { theme: Theme; icon: IconName; text: string; tint?: string }) {
  return (
    <Box flexDirection="row" alignItems="center" gap="xs" height={40} paddingHorizontal="s">
      <Icon name={icon} size={18} color={tint ?? theme.textMuted} />
      <Text variant="chip" numberOfLines={1} style={tint ? { color: tint } : undefined}>
        {text}
      </Text>
    </Box>
  );
}

/**
 * One line at a fixed height under the header. Quiet by default; a warning
 * colours the icon and text, a critical message fills the strip.
 */
export function StatusStrip({
  theme,
  severity,
  text,
  icon,
  tint,
}: {
  theme: Theme;
  severity: Severity | 'quiet';
  text: string;
  icon?: IconName;
  tint?: string;
}) {
  const critical = severity === 'critical';
  const colour =
    tint ?? (critical ? theme.onDark : severity === 'warning' ? theme.warning : severity === 'info' ? theme.text : theme.textMuted);
  const iconName: IconName =
    icon ?? (critical ? 'alert-octagon' : severity === 'warning' ? 'alert' : severity === 'info' ? 'information-outline' : 'circle-small');
  return (
    <Box
      height={36}
      flexDirection="row"
      alignItems="center"
      gap="xs"
      paddingHorizontal="s"
      borderRadius="s"
      style={{ backgroundColor: critical ? theme.critical : 'transparent' }}
    >
      <Icon name={iconName} size={16} color={colour} />
      <Text variant={severity === 'quiet' ? 'strip' : 'stripStrong'} numberOfLines={1} flexShrink={1} style={{ color: colour }}>
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
  icon,
  style,
}: {
  theme: Theme;
  title: string;
  onPress: () => void;
  disabled?: boolean;
  big?: boolean;
  variant?: 'default' | 'accent' | 'record' | 'recording' | 'danger' | 'primary';
  icon?: IconName;
  style?: StyleProp<ViewStyle>;
}) {
  const skin =
    variant === 'accent'
      ? { bg: theme.accent, border: theme.accent, fg: theme.onDark }
      : variant === 'record'
        ? { bg: theme.critical, border: theme.critical, fg: theme.onDark }
        : variant === 'recording'
          ? { bg: theme.text, border: theme.text, fg: theme.bg }
          : variant === 'danger'
            ? { bg: 'transparent', border: theme.critical, fg: theme.text }
            : variant === 'primary'
              ? { bg: theme.text, border: theme.text, fg: theme.bg }
              : { bg: theme.surface2, border: theme.surface2, fg: theme.text };
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
          borderWidth: 1.5,
          flexDirection: 'row',
          gap: spacing.xs,
          alignItems: 'center',
          justifyContent: 'center',
          backgroundColor: skin.bg,
          borderColor: skin.border,
          opacity: disabled ? 0.4 : pressed ? 0.8 : 1,
        },
        style,
      ]}
    >
      {icon && <Icon name={icon} size={18} color={skin.fg} />}
      <Text variant={big ? 'buttonBig' : 'button'} numberOfLines={1} style={{ color: skin.fg }}>
        {title}
      </Text>
    </Pressable>
  );
}

/** The bottom tab bar as one segmented control. */
export function SegmentedTabs<T extends string>({
  theme,
  items,
  value,
  onChange,
}: {
  theme: Theme;
  items: { key: T; label: string; icon: IconName }[];
  value: T;
  onChange: (key: T) => void;
}) {
  return (
    <Box flexDirection="row" padding="xxs" borderRadius="m" style={{ backgroundColor: theme.surface2 }}>
      {items.map((it) => {
        const active = it.key === value;
        return (
          <Pressable
            key={it.key}
            accessibilityRole="tab"
            accessibilityState={{ selected: active }}
            onPress={() => onChange(it.key)}
            style={{
              flex: 1,
              height: 44,
              borderRadius: borderRadii.s,
              flexDirection: 'row',
              gap: spacing.xs,
              alignItems: 'center',
              justifyContent: 'center',
              backgroundColor: active ? theme.text : 'transparent',
            }}
          >
            <Icon name={it.icon} size={18} color={active ? theme.bg : theme.textMuted} />
            <Text variant="button" style={{ color: active ? theme.bg : theme.textMuted }}>
              {it.label}
            </Text>
          </Pressable>
        );
      })}
    </Box>
  );
}

/** A surface card with an optional title row (title left, value right). */
export function Card({
  theme,
  title,
  right,
  children,
}: {
  theme: Theme;
  title?: string;
  right?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <Box borderRadius="l" padding="m" gap="s" style={{ backgroundColor: theme.surface }}>
      {(title || right) && (
        <Box flexDirection="row" alignItems="center" justifyContent="space-between" gap="s">
          {title ? <Text variant="cardTitle">{title}</Text> : <Box />}
          {right}
        </Box>
      )}
      {children}
    </Box>
  );
}

/** A read-out tile: small label, big value, muted unit. */
export function Tile({
  theme,
  label,
  value,
  unit,
}: {
  theme: Theme;
  label: string;
  value: string;
  unit?: string;
}) {
  return (
    <Box flexGrow={1} flexBasis="30%" borderRadius="m" paddingHorizontal="m" paddingVertical="s" gap="xxs" style={{ backgroundColor: theme.surface }}>
      <Text variant="tileKey" numberOfLines={1}>
        {label}
      </Text>
      <Box flexDirection="row" alignItems="baseline" gap="xs">
        <Text variant="tileValue" numberOfLines={1} adjustsFontSizeToFit>
          {value}
        </Text>
        {unit && value !== '—' && (
          <Text variant="tileUnit" numberOfLines={1}>
            {unit}
          </Text>
        )}
      </Box>
    </Box>
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
  // The parent re-renders at the sample rate and passes a fresh onDone each
  // time; keying the timer on it restarted the 3.5 s countdown on every sample,
  // so a toast never cleared while a sensor was streaming.
  const done = useRef(onDone);
  done.current = onDone;
  useEffect(() => {
    const t = setTimeout(() => done.current(id), 3500);
    return () => clearTimeout(t);
  }, [id]);
  return (
    <Box pointerEvents="none" position="absolute" left={0} right={0} bottom={spacing.xxl * 4} alignItems="center">
      <Box paddingHorizontal="l" paddingVertical="m" borderRadius="pill" maxWidth="90%" style={{ backgroundColor: theme.text }}>
        <Text variant="toast">{text}</Text>
      </Box>
    </Box>
  );
}

/** The legend strip for a chart with two or more series. */
export function Legend({ items }: { theme?: Theme; items: [string, string][] }) {
  return (
    <Box flexDirection="row" alignItems="center" gap="m">
      {items.map(([label, colour]) => (
        <Box key={label} flexDirection="row" alignItems="center" gap="xs">
          <Box width={10} height={10} borderRadius="pill" style={{ backgroundColor: colour }} />
          <Text variant="legend">{label}</Text>
        </Box>
      ))}
    </Box>
  );
}
