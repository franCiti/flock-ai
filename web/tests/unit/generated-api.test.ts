// @vitest-environment node
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const apiDir = new URL('../../src/api/', import.meta.url);

describe('generated API types', () => {
  it('match the OpenAPI copy (run `npm run generate:api` if not)', () => {
    const cli = fileURLToPath(
      new URL('../../node_modules/openapi-typescript/bin/cli.js', import.meta.url),
    );
    const spec = fileURLToPath(new URL('openapi.json', apiDir));
    const generated = execFileSync(process.execPath, [cli, spec], { encoding: 'utf8' });

    const committed = readFileSync(new URL('schema.ts', apiDir), 'utf8');

    expect(committed.replace(/\r\n/g, '\n')).toBe(generated.replace(/\r\n/g, '\n'));
  });
});
