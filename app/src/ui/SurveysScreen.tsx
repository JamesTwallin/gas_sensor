// Recorded CSVs: show one on the map, share one to get it onto a computer, open
// one from elsewhere (Files, Drive, an email), or delete one.

import * as DocumentPicker from 'expo-document-picker';
import { File } from 'expo-file-system';
import { useCallback, useEffect, useState } from 'react';
import { Alert, Modal, useWindowDimensions } from 'react-native';
import type { AppController, UiState } from '../controller';
import type { HeatMode } from '../core/heatmap';
import type { SurveyFile } from '../services/recorder';
import { Btn, H2, Hint } from './components';
import { fmtSize, fmtWhen } from './format';
import { SurveyMap } from './SurveyMap';
import { Box, Text } from './restyle';
import type { Theme } from './theme';

// The inline map takes a share of the screen rather than a fixed height, so the
// top of the Surveys list always peeks out under it. Drags on the map pan the
// map, so the list showing is the main cue that the page scrolls.
const MAP_HEIGHT = 380;
const MAP_SCREEN_SHARE = 0.38;

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
  const { height: windowHeight } = useWindowDimensions();
  const inlineMapHeight = Math.min(MAP_HEIGHT, Math.round(windowHeight * MAP_SCREEN_SHARE));
  const points = controller.trackPoints();
  const [heatMode, setHeatMode] = useState<HeatMode>('spikes');
  const [fullMap, setFullMap] = useState(false);
  const trackLen = points.length;
  const shown = state.shownSurvey;
  const fail = (e: unknown) => controller.toast(`Failed: ${e instanceof Error ? e.message : String(e)}`);

  const refresh = useCallback(async () => {
    setFiles(await controller.listSurveys());
  }, [controller]);

  // The map wants a position even before anything is connected.
  useEffect(() => {
    controller.startGps();
  }, [controller]);

  // Re-read after every flush, so the size of the file being recorded moves.
  useEffect(() => {
    void refresh();
  }, [refresh, state.recRows, state.recFileName]);

  const onShare = async (name: string) => {
    try {
      await controller.shareSurvey(name);
    } catch (e) {
      fail(e);
    }
  };

  const onShow = async (name: string | null) => {
    try {
      await controller.showSurvey(name);
    } catch (e) {
      fail(e);
    }
  };

  const onOpen = async () => {
    try {
      // Any type: CSVs come through as text/csv, text/plain or octet-stream
      // depending on where they live, so the file is checked by reading it.
      const res = await DocumentPicker.getDocumentAsync({ type: '*/*', copyToCacheDirectory: true });
      if (res.canceled || !res.assets.length) return;
      const asset = res.assets[0];
      const name = await controller.importSurvey(asset.name, await new File(asset.uri).text());
      await refresh();
      controller.toast(`Opened ${name}`);
    } catch (e) {
      fail(e);
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
            fail(e);
          }
        },
      },
    ]);
  };

  return (
    <Box>
      <H2>Survey map</H2>
      <Hint>
        {shown
          ? `Showing ${shown}.`
          : state.recording
            ? 'Live heatmap of this recording. Switch between the raw reading and spikes, and tap a square to read it.'
            : trackLen
              ? 'The last recording. Tap Record to start a new trace.'
              : 'Tap Record and the route you walk is drawn here as you go.'}
      </Hint>
      {shown && (
        <Box flexDirection="row" marginTop="xs">
          <Btn
            theme={theme}
            title={state.recording ? 'Back to this recording' : 'Back to live map'}
            onPress={() => void onShow(null)}
          />
        </Box>
      )}
      <Box marginTop="s" marginBottom="l">
        <SurveyMap
          key={shown ?? 'live'}
          state={state}
          points={points}
          theme={theme}
          height={inlineMapHeight}
          mode={heatMode}
          onModeChange={setHeatMode}
          onToggleFullscreen={() => setFullMap(true)}
          fitHere={!shown}
        />
        <Modal
          visible={fullMap}
          animationType="fade"
          statusBarTranslucent
          navigationBarTranslucent
          onRequestClose={() => setFullMap(false)}
        >
          <SurveyMap
            state={state}
            points={points}
            theme={theme}
            height={MAP_HEIGHT}
            mode={heatMode}
            onModeChange={setHeatMode}
            fullscreen
            onToggleFullscreen={() => setFullMap(false)}
            fitHere={!shown}
          />
        </Modal>
      </Box>
      <H2>Surveys</H2>
      <Hint>Stored in app storage. Share a CSV to get it onto a computer, or open one saved elsewhere.</Hint>
      <Box flexDirection="row" marginTop="s">
        <Btn theme={theme} title="Open a CSV…" onPress={() => void onOpen()} />
      </Box>
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
                {f.name === shown ? ' · on map' : ''}
              </Text>
              <Text variant="rowMeta">
                {fmtSize(f.size)}
                {f.mtime ? ` · ${fmtWhen(f.mtime)}` : ''}
              </Text>
              <Box flexDirection="row" gap="s" marginTop="xs" flexWrap="wrap">
                {f.name !== shown && !active && (
                  <Btn theme={theme} title="Show on map" onPress={() => void onShow(f.name)} />
                )}
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
