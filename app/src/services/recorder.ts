// Survey recording: CSV rows are buffered in memory and appended to app storage
// every few seconds, so a crash or a killed app loses at most one batch.
//
// Files live in <documents>/surveys/. On Android that is the app-private files
// dir; on iOS it is the Documents folder, which UIFileSharingEnabled exposes to
// the Files app (see app.json). The expo-file-system API is synchronous, so the
// flush still runs behind a promise queue to keep batches strictly ordered.

import { Directory, File, Paths } from 'expo-file-system';
import * as Sharing from 'expo-sharing';
import { CSV_HEADER, surveyFileName } from '../core/csv';

export const SURVEY_DIR = 'surveys';
export const FLUSH_INTERVAL_MS = 3000;

export interface SurveyFile {
  name: string;
  size: number;
  mtime: number;
}

function surveyDir(): Directory {
  return new Directory(Paths.document, SURVEY_DIR);
}

function surveyFile(name: string): File {
  return new File(surveyDir(), name);
}

export class Recorder {
  fileName: string | null = null;
  rows = 0;
  startedAt = 0;
  lastError: string | null = null;
  private buffer: string[] = [];
  private timer: ReturnType<typeof setInterval> | null = null;
  private queue: Promise<void> = Promise.resolve();

  constructor(private onChange: () => void = () => {}) {}

  get recording(): boolean {
    return this.fileName !== null;
  }

  async start(): Promise<string> {
    if (this.fileName) return this.fileName;
    const name = surveyFileName(Date.now());
    const dir = surveyDir();
    if (!dir.exists) dir.create({ intermediates: true });
    const file = surveyFile(name);
    file.create({ overwrite: true });
    file.write(CSV_HEADER + '\n');
    this.fileName = name;
    this.rows = 0;
    this.startedAt = Date.now();
    this.lastError = null;
    this.buffer = [];
    this.timer = setInterval(() => void this.flush(), FLUSH_INTERVAL_MS);
    this.onChange();
    return name;
  }

  add(row: string): void {
    if (!this.fileName) return;
    this.buffer.push(row);
    this.rows++;
  }

  flush(): Promise<void> {
    const name = this.fileName;
    if (!name || this.buffer.length === 0) return this.queue;
    const batch = this.buffer;
    this.buffer = [];
    this.queue = this.queue.then(async () => {
      try {
        surveyFile(name).write(batch.join('\n') + '\n', { append: true });
        if (this.lastError) {
          this.lastError = null;
          this.onChange();
        }
      } catch (e) {
        // Keep the rows and retry on the next flush.
        if (this.fileName === name) this.buffer = batch.concat(this.buffer);
        this.lastError = e instanceof Error ? e.message : String(e);
        this.onChange();
      }
    });
    return this.queue;
  }

  async stop(): Promise<string | null> {
    const name = this.fileName;
    if (!name) return null;
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
    await this.flush();
    this.fileName = null;
    this.onChange();
    return name;
  }

  static async list(): Promise<SurveyFile[]> {
    try {
      const dir = surveyDir();
      if (!dir.exists) return [];
      return dir
        .list()
        .filter((e): e is File => e instanceof File && e.name.endsWith('.csv'))
        .map((f) => ({ name: f.name, size: f.size, mtime: f.lastModified ?? 0 }))
        .sort((a, b) => b.name.localeCompare(a.name));
    } catch {
      return []; // directory not created yet
    }
  }

  static async read(name: string): Promise<string> {
    const file = surveyFile(name);
    if (!file.exists) throw new Error(`${name} is gone`);
    return file.text();
  }

  /**
   * Save CSV text picked from elsewhere (Files, Drive, an email) into the survey
   * folder under a free name based on `name`; returns the name used.
   */
  static async importText(name: string, text: string): Promise<string> {
    const dir = surveyDir();
    if (!dir.exists) dir.create({ intermediates: true });
    const base = (name.replace(/\.csv$/i, '').replace(/[^\w.-]+/g, '_') || 'imported').slice(0, 80);
    let out = `${base}.csv`;
    for (let n = 2; surveyFile(out).exists; n++) out = `${base}_${n}.csv`;
    const file = surveyFile(out);
    file.create();
    file.write(text);
    return out;
  }

  static async remove(name: string): Promise<void> {
    surveyFile(name).delete();
  }

  static async share(name: string): Promise<void> {
    const file = surveyFile(name);
    if (!file.exists) throw new Error(`${name} is gone`);
    if (!(await Sharing.isAvailableAsync())) throw new Error('Sharing is not available on this device');
    await Sharing.shareAsync(file.uri, {
      mimeType: 'text/csv',
      UTI: 'public.comma-separated-values-text',
      dialogTitle: `CH4 survey ${name}`,
    });
  }
}
