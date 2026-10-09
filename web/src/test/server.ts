import { HttpResponse, http } from 'msw';
import { setupServer } from 'msw/node';
import type { Credentials, CurrentUser } from '../api/auth.ts';

/** Simulated Core API. Every test starts without handlers; unknown requests fail. */
export const server = setupServer();

export const testUser: CurrentUser = { username: 'demo' };
export const validCredentials: Credentials = { username: 'demo', password: 'demo-password' };

/** Session endpoints that behave like the Core API: a valid login opens a session. */
export function mockAuthApi(options: { signedIn?: boolean } = {}) {
  let signedIn = options.signedIn ?? false;
  const loginBodies: unknown[] = [];

  server.use(
    http.get('*/api/auth/me', () =>
      signedIn ? HttpResponse.json(testUser) : new HttpResponse(null, { status: 401 }),
    ),
    http.post('*/api/auth/login', async ({ request }) => {
      const body = (await request.json()) as Credentials;
      loginBodies.push(body);
      signedIn =
        body.username === validCredentials.username && body.password === validCredentials.password;
      return new HttpResponse(null, { status: signedIn ? 204 : 401 });
    }),
    http.post('*/api/auth/logout', () => {
      signedIn = false;
      return new HttpResponse(null, { status: 204 });
    }),
  );

  return { loginBodies };
}
