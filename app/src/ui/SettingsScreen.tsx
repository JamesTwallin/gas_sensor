// Processing + app settings, the simulator test bench, and the device read-out.
// Number fields keep their own draft string while being typed, so a half-typed
// value ("0.") does not get sanitised out from under the keyboard.

import { useEffect, useState } from 'react';
import { Switch, TextInput, type StyleProp, type TextStyle } from 'react-native';
import type { AppSettings } from '../core/settings';
import type { AppController, UiState } from '../controller';
import { Btn, H2, H3, Hint } from './components';
import { Box, Text, borderRadii, sizes, spacing } from './restyle';
import type { Theme } from './theme';

interface Field {
  key: keyof AppSettings;
  label: string;
  hint?: string;
  /** stored value = shown value × scale */
  scale?: number;
  min?: number;
  max?: number;
}

const FIELDS: Field[] = [
  { key: 'simulate', label: 'Simulated device', hint: 'Fake board with random plumes, for testing' },
  {
    key: 'usbBridge',
    label: 'USB bridge via PC',
    hint: 'Board plugged into a PC running tools/serial_bridge.py. Always used in Expo Go (no Bluetooth there)',
  },
  { key: 'bridgeHost', label: 'Bridge PC address', hint: 'Blank = the PC running Expo' },
  { key: 'lightTheme', label: 'Light theme', hint: 'Easier to read in direct sun' },
  { key: 'keepAwake', label: 'Keep screen awake', hint: 'While connected or recording' },
  { key: 'driveLed', label: 'Drive board LED', hint: 'Green / amber / red from CH4 class' },
  { key: 'warmupMs', label: 'Warm-up (min)', hint: 'From sensor power-on', scale: 60_000, min: 0 },
  { key: 'baselineMs', label: 'Baselining (min)', scale: 60_000, min: 0 },
  { key: 'bgWindowMs', label: 'Baseline window (min)', scale: 60_000, min: 0.5 },
  { key: 'bgPercentile', label: 'Baseline percentile', hint: '15 = 15th percentile', scale: 0.01, min: 1, max: 50 },
  { key: 'classWindowMs', label: 'Class window (min)', hint: 'HIGH/MED/LOW range', scale: 60_000, min: 1, max: 60 },
  { key: 'classRangeFloorMv', label: 'Class range floor (mV)', min: 0 },
  { key: 'intervalMs', label: 'Sample interval (ms)', hint: '100–5000, sent to the board', min: 100, max: 5000 },
];

function inputStyle(theme: Theme, wide: boolean): StyleProp<TextStyle> {
  return {
    minWidth: wide ? 168 : 96,
    minHeight: sizes.input,
    borderWidth: 2,
    borderRadius: borderRadii.s,
    paddingHorizontal: spacing.m,
    fontSize: 17,
    fontWeight: '700',
    textAlign: 'right',
    color: theme.text,
    borderColor: theme.border,
    backgroundColor: theme.surface,
  };
}

function NumberField({
  field,
  value,
  theme,
  onCommit,
}: {
  field: Field;
  value: number;
  theme: Theme;
  onCommit: (stored: number) => void;
}) {
  const shown = +(value / (field.scale ?? 1)).toFixed(3);
  const [draft, setDraft] = useState(String(shown));

  // Follow the store when it changes from elsewhere (e.g. a reset), not while typing.
  useEffect(() => {
    setDraft(String(shown));
  }, [shown]);

  const commit = () => {
    let n = parseFloat(draft);
    if (!Number.isFinite(n)) return setDraft(String(shown));
    if (field.min !== undefined) n = Math.max(field.min, n);
    if (field.max !== undefined) n = Math.min(field.max, n);
    setDraft(String(n));
    onCommit(n * (field.scale ?? 1));
  };

  return (
    <TextInput
      value={draft}
      onChangeText={setDraft}
      onBlur={commit}
      onSubmitEditing={commit}
      keyboardType="decimal-pad"
      returnKeyType="done"
      selectTextOnFocus
      style={inputStyle(theme, false)}
    />
  );
}

function TextField({
  value,
  theme,
  placeholder,
  onCommit,
}: {
  value: string;
  theme: Theme;
  placeholder?: string;
  onCommit: (text: string) => void;
}) {
  const [draft, setDraft] = useState(value);
  useEffect(() => {
    setDraft(value);
  }, [value]);
  const commit = () => onCommit(draft.trim());
  return (
    <TextInput
      value={draft}
      onChangeText={setDraft}
      onBlur={commit}
      onSubmitEditing={commit}
      placeholder={placeholder}
      placeholderTextColor={theme.textMuted}
      keyboardType="url"
      autoCapitalize="none"
      autoCorrect={false}
      returnKeyType="done"
      selectTextOnFocus
      style={[inputStyle(theme, true), { fontSize: 16, fontWeight: '600' }]}
    />
  );
}

export function SettingsScreen({
  state,
  controller,
  theme,
}: {
  state: UiState;
  controller: AppController;
  theme: Theme;
}) {
  const { settings, info } = state;
  const sim = state.linkKind === 'sim';

  return (
    <Box>
      <H2>Settings</H2>
      {FIELDS.map((f) => {
        const v = settings[f.key];
        return (
          <Box
            key={f.key}
            flexDirection="row"
            alignItems="center"
            justifyContent="space-between"
            gap="m"
            paddingVertical="m"
            borderBottomWidth={1}
            style={{ borderBottomColor: theme.border }}
          >
            <Box flexShrink={1} flexGrow={1} gap="xxs">
              <Text variant="label">{f.label}</Text>
              {f.hint && <Text variant="labelHint">{f.hint}</Text>}
            </Box>
            {typeof v === 'boolean' ? (
              <Switch
                value={v}
                onValueChange={(next) => void controller.updateSetting(f.key, next as never)}
                trackColor={{ true: theme.good, false: theme.border }}
              />
            ) : typeof v === 'string' ? (
              <TextField
                value={v}
                theme={theme}
                placeholder="auto"
                onCommit={(text) => void controller.updateSetting(f.key, text as never)}
              />
            ) : (
              <NumberField
                field={f}
                value={v as number}
                theme={theme}
                onCommit={(stored) => void controller.updateSetting(f.key, stored as never)}
              />
            )}
          </Box>
        );
      })}

      {sim && (
        <Box>
          <H3>Simulator</H3>
          <Box flexDirection="row" gap="s" flexWrap="wrap" marginVertical="s">
            <Btn theme={theme} title="Press BOOT" onPress={() => controller.simPressButton()} />
            <Btn theme={theme} title="Drop link" onPress={() => controller.simDropLink()} />
            <Btn theme={theme} title="Toggle USB" onPress={() => controller.simToggleUsb()} />
            <Btn theme={theme} title="Toggle heaters" onPress={() => controller.simToggleHeaters()} />
          </Box>
          <Hint>Board LED (opcode 0x03): rgb({(state.simLed ?? [0, 0, 0]).join(', ')})</Hint>
        </Box>
      )}

      <Box flexDirection="row" gap="s" flexWrap="wrap" marginVertical="m">
        <Btn theme={theme} title="Identify (blink LED)" onPress={() => controller.identify()} />
      </Box>

      {state.linked && (
        <Hint>
          {`${state.linkName ?? '?'} · fw ${info.fw} · board ${info.board} · RL ${info.rl_ohm} Ω · ` +
            `tap ×${info.tap_ratio} · VC ${info.vc_mv} mV · ${info.interval_ms} ms` +
            (info.heater_mv ? ` · heater ${info.heater_mv} mV` : '')}
        </Hint>
      )}
    </Box>
  );
}
