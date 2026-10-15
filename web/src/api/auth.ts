import { ApiError, api, apiFetch } from './client.ts';
import { CSRF_COOKIE, readCookie } from './csrf.ts';
import type { components } from './schema.ts';

export type Credentials = components['schemas']['LoginRequest'];
export type CurrentUser = components['schemas']['CurrentUser'];

/** The username or password is wrong. */
export class InvalidCredentialsError extends Error {
  constructor() {
    super('Invalid username or password');
    this.name = 'InvalidCredentialsError';
  }
}

/** Returns the signed-in user, or null when there is no session. */
export async function fetchCurrentUser(): Promise<CurrentUser | null> {
  const { data, response } = await api.GET('/api/auth/me');
  if (response.status === 401) {
    return null;
  }
  if (!response.ok || data === undefined) {
    throw new ApiError(response.status);
  }
  return data;
}

/** Starts a session; the Core API sets the session cookie. */
export async function login(credentials: Credentials): Promise<void> {
  // The CSRF cookie comes with any response, but a logout clears it: without one, ask for it first.
  if (readCookie(CSRF_COOKIE) === undefined) {
    await api.GET('/api/auth/me');
  }
  const { response } = await api.POST('/api/auth/login', { body: credentials });
  if (response.status === 401) {
    throw new InvalidCredentialsError();
  }
  if (!response.ok) {
    throw new ApiError(response.status);
  }
}

/**
 * Ends the session. Spring Security answers it before any controller, so it is not in the
 * OpenAPI spec and goes through the plain client.
 */
export async function logout(): Promise<void> {
  const response = await apiFetch('/api/auth/logout', { method: 'POST' });
  if (!response.ok) {
    throw new ApiError(response.status);
  }
}
