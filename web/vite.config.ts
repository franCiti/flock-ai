import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

// Same origin as in production (plan 6.1): the dev server proxies the API and its docs.
const coreApiUrl = process.env.CORE_API_URL ?? 'http://localhost:8080';

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': coreApiUrl,
      '/docs': coreApiUrl,
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}', 'tests/unit/**/*.test.ts'],
  },
});
