import { ApiError, apiFetch } from './client.ts';

// TODO(T32): the Core API does not publish /api/auth/* yet, so these types and calls are written by
// hand from plan 6.2 and 6.3. Once T32 adds the endpoints, regenerate the client (npm run
// generate:api) and replace them with the generated `api` client.

export interface Credentials {
  username: string;
  password: string;
}

export interface CurrentUser {
  username: string;
}

/** The username or password is wrong. */
export class InvalidCredentialsError extends Error {
  constructor() {
    super('Invalid username or password');
    this.name = 'InvalidCredentialsError';
  }
}

/** Returns the signed-in user, or null when there is no session. */
export async function fetchCurrentUser(): Promise<CurrentUser | null> {
  const response = await apiFetch('/api/auth/me');
  if (response.status === 401) {
    return null;
  }
  if (!response.ok) {
    throw new ApiError(response.status);
  }
  return (await response.json()) as CurrentUser;
}

/** Starts a session; the Core API sets the session cookie. */
export async function login(credentials: Credentials): Promise<void> {
  const response = await apiFetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(credentials),
  });
  if (response.status === 401) {
    throw new InvalidCredentialsError();
  }
  if (!response.ok) {
    throw new ApiError(response.status);
  }
}

/** Ends the session. */
export async function logout(): Promise<void> {
  const response = await apiFetch('/api/auth/logout', { method: 'POST' });
  if (!response.ok) {
    throw new ApiError(response.status);
  }
}
