import { defineConfig } from 'vitest/config';

// The unit tests only cover src/core and the pure chart geometry in src/ui --
// no React Native module is imported, so plain node is the right environment.
export default defineConfig({
  test: {
    include: ['tests/**/*.test.ts'],
    environment: 'node',
  },
});
