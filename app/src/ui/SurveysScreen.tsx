// Recorded CSVs: share one to get it onto a computer, or delete it.

import { useCallback, useEffect, useState } from 'react';
import { Alert, StyleSheet, Text, View } from 'react-native';
import type { AppController, UiState } from '../app/controller';
import type { SurveyFile } from '../services/recorder';
import { Btn, H2, Hint } from './components';
import { fmtSize, fmtWhen } from './format';
import type { Theme } from './theme';

export function SurveysScreen({
  state,
  controller,
  theme,
}: {
  state: UiState;
  controller: AppController;
  theme: Theme;
}) {
  const [files, setFiles] = useState<SurveyFile[] | null>(null);

  const refresh = useCallback(async () => {
    setFiles(await controller.listSurveys());
  }, [controller]);

  // Re-read after every flush, so the size of the file being recorded moves.
  useEffect(() => {
    void refresh();
  }, [refresh, state.recRows, state.recFileName]);

  const onShare = async (name: string) => {
    try {
      await controller.shareSurvey(name);
    } catch (e) {
      controller.toast(`Failed: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  const onDelete = (name: string) => {
    Alert.alert('Delete survey', `Delete ${name}? This cannot be undone.`, [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Delete',
        style: 'destructive',
        onPress: async () => {
          try {
            await controller.deleteSurvey(name);
            await refresh();
          } catch (e) {
            controller.toast(`Failed: ${e instanceof Error ? e.message : String(e)}`);
          }
        },
      },
    ]);
  };

  return (
    <View>
      <H2 theme={theme}>Surveys</H2>
      <Hint theme={theme}>
        Stored in app storage. Share a CSV to your computer and drop it in tools/data/.
      </Hint>
      {files === null && <Hint theme={theme}>Loading…</Hint>}
      {files !== null && files.length === 0 && (
        <Hint theme={theme}>No surveys yet. Connect, then tap Record.</Hint>
      )}
      {files?.map((f) => {
        const active = f.name === state.recFileName;
        return (
          <View key={f.name} style={[styles.row, { backgroundColor: theme.surface, borderColor: theme.border }]}>
            <Text style={[styles.name, { color: theme.text }]}>
              {f.name}
              {active ? ' · recording' : ''}
            </Text>
            <Text style={[styles.meta, { color: theme.textMuted }]}>
              {fmtSize(f.size)}
              {f.mtime ? ` · ${fmtWhen(f.mtime)}` : ''}
            </Text>
            <View style={styles.btnRow}>
              <Btn theme={theme} title="Share / export" onPress={() => void onShare(f.name)} />
              {!active && <Btn theme={theme} title="Delete" variant="danger" onPress={() => onDelete(f.name)} />}
            </View>
          </View>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { borderRadius: 12, borderWidth: 1, padding: 12, marginBottom: 10, gap: 4 },
  name: { fontSize: 18, fontWeight: '700' },
  meta: { fontSize: 15 },
  btnRow: { flexDirection: 'row', gap: 8, marginTop: 8, flexWrap: 'wrap' },
});
