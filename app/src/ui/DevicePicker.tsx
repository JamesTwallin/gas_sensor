// Capacitor's requestDevice() gave us a native chooser for free; react-native-ble-plx
// does not, so this modal is the picker: live scan results, strongest first.

import { Modal, Pressable, StyleSheet, Text, View } from 'react-native';
import type { AppController, UiState } from '../app/controller';
import { Btn, H2, Hint } from './components';
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
      <View style={styles.backdrop}>
        <View style={[styles.sheet, { backgroundColor: theme.bg, borderColor: theme.border }]}>
          <H2 theme={theme}>Choose your sensor</H2>
          {state.scanError ? (
            <Hint theme={theme}>{state.scanError}</Hint>
          ) : state.scanned.length === 0 ? (
            <Hint theme={theme}>Scanning for CH4 sensors… make sure the board is powered on and nearby.</Hint>
          ) : (
            <Hint theme={theme}>Tap a board to connect.</Hint>
          )}

          {state.scanned.map((d) => (
            <Pressable
              key={d.id}
              onPress={() => controller.connectTo(d)}
              style={({ pressed }) => [
                styles.row,
                { backgroundColor: theme.surface2, borderColor: theme.border, opacity: pressed ? 0.85 : 1 },
              ]}
            >
              <View style={{ flexShrink: 1 }}>
                <Text style={[styles.name, { color: theme.text }]} numberOfLines={1}>
                  {d.name}
                </Text>
                <Text style={[styles.id, { color: theme.textMuted }]} numberOfLines={1}>
                  {d.id}
                </Text>
              </View>
              <Text style={[styles.rssi, { color: theme.textMuted }]}>
                {d.rssi === null ? '' : `${d.rssi} dBm`}
              </Text>
            </Pressable>
          ))}

          <View style={styles.actions}>
            <Btn theme={theme} title="Cancel" onPress={() => controller.cancelScan()} style={{ flex: 1 }} />
          </View>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { flex: 1, justifyContent: 'flex-end', backgroundColor: 'rgba(0,0,0,0.55)' },
  sheet: {
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    borderWidth: 2,
    paddingHorizontal: 16,
    paddingTop: 12,
    paddingBottom: 28,
    maxHeight: '80%',
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
    borderWidth: 2,
    borderRadius: 12,
    padding: 12,
    marginBottom: 8,
    minHeight: 56,
  },
  name: { fontSize: 19, fontWeight: '700' },
  id: { fontSize: 13 },
  rssi: { fontSize: 15, fontWeight: '600' },
  actions: { flexDirection: 'row', marginTop: 8 },
});
