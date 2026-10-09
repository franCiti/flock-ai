import { existsSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

// Login against a running Core API (`npm run test:api`). It is expected to fail until T32 adds
// the auth endpoints; passing it is part of T32's definition of done.
//
// Needs the Core API listening on CORE_API_URL and the initial user of the repository .env
// (ADMIN_USERNAME, ADMIN_PASSWORD).

const envFile = new URL('../../../.env', import.meta.url);
if (existsSync(envFile)) {
  process.loadEnvFile(envFile);
}

const baseUrl = process.env.CORE_API_URL ?? 'http://localhost:8080';
const username = process.env.ADMIN_USERNAME ?? '';
const password = process.env.ADMIN_PASSWORD ?? '';

/** A minimal browser: keeps the cookies and sends the CSRF token back, like the web app. */
class Browser {
  private readonly cookies = new Map<string, string>();

  async request(method: string, path: string, body?: unknown): Promise<Response> {
    const headers = new Headers({ Cookie: this.cookieHeader() });
    const csrfToken = this.cookies.get('XSRF-TOKEN');
    if (method !== 'GET' && csrfToken !== undefined) {
      headers.set('X-XSRF-TOKEN', decodeURIComponent(csrfToken));
    }
    if (body !== undefined) {
      headers.set('Content-Type', 'application/json');
    }
    const response = await fetch(new URL(path, baseUrl), {
      method,
      headers,
      redirect: 'manual',
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    for (const cookie of response.headers.getSetCookie()) {
      const [pair = ''] = cookie.split(';');
      const separator = pair.indexOf('=');
      this.cookies.set(pair.slice(0, separator), pair.slice(separator + 1));
    }
    return response;
  }

  private cookieHeader(): string {
    return [...this.cookies].map(([name, value]) => `${name}=${value}`).join('; ');
  }
}

describe('Core API login', () => {
  it('has the initial user configured in .env', () => {
    expect(username, 'ADMIN_USERNAME').not.toBe('');
    expect(password, 'ADMIN_PASSWORD').not.toBe('');
  });

  it('rejects /api/auth/me without a session', async () => {
    const response = await new Browser().request('GET', '/api/auth/me');

    expect(response.status).toBe(401);
  });

  it('rejects a wrong password', async () => {
    const browser = new Browser();
    await browser.request('GET', '/api/auth/me');

    const response = await browser.request('POST', '/api/auth/login', {
      username,
      password: `${password}-wrong`,
    });

    expect(response.status).toBe(401);
  });

  it('signs in with the initial user, reads the session and signs out', async () => {
    const browser = new Browser();
    // The first request hands out the CSRF token cookie.
    await browser.request('GET', '/api/auth/me');

    const login = await browser.request('POST', '/api/auth/login', { username, password });
    expect(login.ok, `login status ${String(login.status)}`).toBe(true);

    const me = await browser.request('GET', '/api/auth/me');
    expect(me.status).toBe(200);
    expect(await me.json()).toMatchObject({ username });

    const logout = await browser.request('POST', '/api/auth/logout');
    expect(logout.ok, `logout status ${String(logout.status)}`).toBe(true);
    expect((await browser.request('GET', '/api/auth/me')).status).toBe(401);
  });
});
