// Capacitor's requestDevice() gave us a native chooser for free; react-native-ble-plx
// does not, so this modal is the picker: live scan results, strongest first.

import { Modal, Pressable } from 'react-native';
import type { AppController, UiState } from '../controller';
import { Btn, H2, Hint } from './components';
import { Box, Text, borderRadii, sizes, spacing } from './restyle';
import type { Theme } from './theme';

export function DevicePicker({
  state,
  controller,
  theme,
}: {
  state: UiState;
  controller: AppController;
  theme: Theme;
}) {
  return (
    <Modal
      visible={state.scanning}
      animationType="slide"
      transparent
      onRequestClose={() => controller.cancelScan()}
    >
      <Box flex={1} justifyContent="flex-end" style={{ backgroundColor: 'rgba(0,0,0,0.55)' }}>
        <Box
          borderTopLeftRadius="l"
          borderTopRightRadius="l"
          borderWidth={2}
          paddingHorizontal="l"
          paddingTop="m"
          paddingBottom="xl"
          maxHeight="80%"
          gap="s"
          style={{ backgroundColor: theme.bg, borderColor: theme.border }}
        >
          <H2>Choose your sensor</H2>
          {state.scanError ? (
            <Hint>{state.scanError}</Hint>
          ) : state.scanned.length === 0 ? (
            <Hint>Scanning for CH4 sensors… make sure the board is powered on and nearby.</Hint>
          ) : (
            <Hint>Tap a board to connect.</Hint>
          )}

          {state.scanned.map((d) => (
            <Pressable
              key={d.id}
              onPress={() => controller.connectTo(d)}
              style={({ pressed }) => ({
                flexDirection: 'row',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: spacing.m,
                borderWidth: 2,
                borderRadius: borderRadii.m,
                padding: spacing.m,
                minHeight: sizes.tapBig,
                backgroundColor: theme.surface2,
                borderColor: theme.border,
                opacity: pressed ? 0.85 : 1,
              })}
            >
              <Box flexShrink={1} gap="xxs">
                <Text variant="rowTitle" numberOfLines={1}>
                  {d.name}
                </Text>
                <Text variant="rowMeta" numberOfLines={1}>
                  {d.id}
                </Text>
              </Box>
              <Text variant="legend">{d.rssi === null ? '' : `${d.rssi} dBm`}</Text>
            </Pressable>
          ))}

          <Box flexDirection="row" marginTop="s">
            <Btn theme={theme} title="Cancel" onPress={() => controller.cancelScan()} style={{ flex: 1 }} />
          </Box>
        </Box>
      </Box>
    </Modal>
  );
}
