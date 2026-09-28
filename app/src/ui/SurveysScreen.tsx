// Recorded CSVs: share one to get it onto a computer, or delete it.

import { useCallback, useEffect, useState } from 'react';
import { Alert } from 'react-native';
import type { AppController, UiState } from '../controller';
import type { SurveyFile } from '../services/recorder';
import { Btn, H2, Hint } from './components';
import { fmtSize, fmtWhen } from './format';
import { Box, Text } from './restyle';
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
    <Box>
      <H2>Surveys</H2>
      <Hint>Stored in app storage. Share a CSV to your computer and drop it in tools/data/.</Hint>
      {files === null && <Hint>Loading…</Hint>}
      {files !== null && files.length === 0 && <Hint>No surveys yet. Connect, then tap Record.</Hint>}
      <Box gap="s" marginTop="s">
        {files?.map((f) => {
          const active = f.name === state.recFileName;
          return (
            <Box
              key={f.name}
              borderRadius="m"
              borderWidth={1}
              padding="m"
              gap="xs"
              style={{ backgroundColor: theme.surface, borderColor: theme.border }}
            >
              <Text variant="rowTitle">
                {f.name}
                {active ? ' · recording' : ''}
              </Text>
              <Text variant="rowMeta">
                {fmtSize(f.size)}
                {f.mtime ? ` · ${fmtWhen(f.mtime)}` : ''}
              </Text>
              <Box flexDirection="row" gap="s" marginTop="xs" flexWrap="wrap">
                <Btn theme={theme} title="Share / export" onPress={() => void onShare(f.name)} />
                {!active && <Btn theme={theme} title="Delete" variant="danger" onPress={() => onDelete(f.name)} />}
              </Box>
            </Box>
          );
        })}
      </Box>
    </Box>
  );
}
