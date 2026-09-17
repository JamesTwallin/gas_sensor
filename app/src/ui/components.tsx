// Shared bits of chrome: pills, banners, buttons, section headings, toast.
// The sizes are the web app's: 48–64 px targets, 17–26 px type, readable at
// arm's length with gloves on.

import { useEffect } from 'react';
import { Pressable, StyleSheet, Text, View, type StyleProp, type ViewStyle } from 'react-native';
import type { LinkStatus } from '../services/device';
import type { Severity, Theme } from './theme';

export function Pill({
  theme,
  children,
  status,
  ghost,
  onPress,
  tint,
}: {
  theme: Theme;
  children: React.ReactNode;
  status?: LinkStatus;
  ghost?: boolean;
  onPress?: () => void;
  tint?: string;
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
    <View
      style={[
        styles.pill,
        { borderColor: tint ?? theme.border, backgroundColor: ghost ? 'transparent' : theme.surface },
      ]}
    >
      {status !== undefined && <View style={[styles.dot, { backgroundColor: dotColour }]} />}
      <Text style={[styles.pillText, { color: tint ?? theme.text }]} numberOfLines={1}>
        {children}
      </Text>
    </View>
  );
  return onPress ? <Pressable onPress={onPress}>{body}</Pressable> : body;
}

export function Banner({ theme, severity, text }: { theme: Theme; severity: Severity; text: string }) {
  const style =
    severity === 'critical'
      ? { backgroundColor: theme.critical, borderColor: theme.critical, color: theme.onDark, fontSize: 18 }
      : severity === 'warning'
        ? { backgroundColor: 'transparent', borderColor: theme.warning, color: theme.text, fontSize: 18 }
        : { backgroundColor: 'transparent', borderColor: theme.border, color: theme.textMuted, fontSize: 16 };
  return (
    <View style={[styles.banner, { backgroundColor: style.backgroundColor, borderColor: style.borderColor }]}>
      <Text style={{ color: style.color, fontSize: style.fontSize, fontWeight: '700' }}>{text}</Text>
    </View>
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
        styles.btn,
        big && styles.btnBig,
        { backgroundColor: skin.bg, borderColor: skin.border, opacity: disabled ? 0.45 : pressed ? 0.85 : 1 },
        style,
      ]}
    >
      <Text style={[styles.btnText, big && styles.btnTextBig, { color: skin.fg }]} numberOfLines={1}>
        {title}
      </Text>
    </Pressable>
  );
}

export function Hint({ theme, children }: { theme: Theme; children: React.ReactNode }) {
  return <Text style={[styles.hint, { color: theme.textMuted }]}>{children}</Text>;
}

export function H2({ theme, children }: { theme: Theme; children: React.ReactNode }) {
  return <Text style={[styles.h2, { color: theme.text }]}>{children}</Text>;
}

export function H3({ theme, children }: { theme: Theme; children: React.ReactNode }) {
  return <Text style={[styles.h3, { color: theme.text }]}>{children}</Text>;
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
    <View pointerEvents="none" style={styles.toastWrap}>
      <Text style={[styles.toast, { backgroundColor: theme.text, color: theme.bg }]}>{text}</Text>
    </View>
  );
}

/** The legend strip above a chart. */
export function Legend({ theme, items, note }: { theme: Theme; items: [string, string][]; note: string }) {
  return (
    <View style={styles.legend}>
      {items.map(([label, colour]) => (
        <View key={label} style={styles.legendItem}>
          <View style={[styles.swatch, { backgroundColor: colour }]} />
          <Text style={{ color: theme.textMuted, fontSize: 15, fontWeight: '600' }}>{label}</Text>
        </View>
      ))}
      <Text style={{ color: theme.textMuted, fontSize: 15, marginLeft: 'auto' }}>{note}</Text>
    </View>
  );
}

export const styles = StyleSheet.create({
  pill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    minHeight: 40,
    paddingHorizontal: 14,
    paddingVertical: 6,
    borderRadius: 999,
    borderWidth: 2,
  },
  pillText: { fontSize: 17, fontWeight: '600' },
  dot: { width: 14, height: 14, borderRadius: 7 },
  banner: { marginBottom: 8, paddingHorizontal: 14, paddingVertical: 12, borderRadius: 10, borderWidth: 2 },
  btn: {
    minHeight: 48,
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 12,
    borderWidth: 2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  btnBig: { minHeight: 64, paddingHorizontal: 6 },
  btnText: { fontSize: 18, fontWeight: '700' },
  btnTextBig: { fontSize: 19 },
  hint: { fontSize: 15, lineHeight: 20, marginVertical: 4 },
  h2: { fontSize: 28, fontWeight: '700', marginVertical: 8 },
  h3: { fontSize: 21, fontWeight: '700', marginTop: 12, marginBottom: 4 },
  toastWrap: { position: 'absolute', left: 0, right: 0, bottom: 24, alignItems: 'center' },
  toast: {
    paddingHorizontal: 18,
    paddingVertical: 12,
    borderRadius: 12,
    fontSize: 18,
    fontWeight: '700',
    overflow: 'hidden',
    maxWidth: '90%',
  },
  legend: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 4 },
  legendItem: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  swatch: { width: 14, height: 14, borderRadius: 3 },
});
