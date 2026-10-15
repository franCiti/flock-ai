import createClient from 'openapi-fetch';
import { withCsrfToken } from './csrf.ts';
import type { paths } from './schema.ts';

/** An API response with an unexpected status. */
export class ApiError extends Error {
  constructor(readonly status: number) {
    super(`Unexpected API response status: ${String(status)}`);
    this.name = 'ApiError';
  }
}

/** Calls the Core API on the same origin (plan 6.1), with the session cookie and CSRF token. */
export function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const request = new Request(new URL(path, window.location.origin), {
    ...init,
    credentials: 'same-origin',
  });
  return fetch(withCsrfToken(request));
}

/** Typed client generated from the Core API OpenAPI spec (plan 6.7). */
export const api = createClient<paths>({
  baseUrl: window.location.origin,
  credentials: 'same-origin',
  fetch: (request: Request) => fetch(withCsrfToken(request)),
});
