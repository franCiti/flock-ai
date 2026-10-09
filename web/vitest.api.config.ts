import { defineConfig } from 'vitest/config';

// Tests against a running Core API (not part of `npm test`). They fail until the endpoints they
// use exist: the login ones arrive with T32.
export default defineConfig({
  test: {
    environment: 'node',
    include: ['tests/api/**/*.test.ts'],
  },
});
