// Small display helpers shared by the screens. Pure.

export const fmtDuration = (ms: number): string => {
  const s = Math.max(0, Math.ceil(ms / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
};

export const signed = (mv: number): string => `${mv >= 0 ? '+' : '−'}${Math.abs(Math.round(mv))} mV`;

export const fmtSize = (bytes: number): string => `${(bytes / 1024).toFixed(1)} KB`;

export const fmtWhen = (epochMs: number): string =>
  epochMs ? new Date(epochMs).toLocaleString() : '';
