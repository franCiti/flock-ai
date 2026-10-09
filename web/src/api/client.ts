import createClient from 'openapi-fetch';
import type { paths } from './schema.ts';

/** Cookie where the Core API leaves the CSRF token, and header where it expects it back (plan 6.2). */
export const CSRF_COOKIE = 'XSRF-TOKEN';
export const CSRF_HEADER = 'X-XSRF-TOKEN';

const UNSAFE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

/** An API response with an unexpected status. */
export class ApiError extends Error {
  constructor(readonly status: number) {
    super(`Unexpected API response status: ${String(status)}`);
    this.name = 'ApiError';
  }
}

export function readCookie(name: string): string | undefined {
  const prefix = `${name}=`;
  const cookie = document.cookie.split('; ').find((entry) => entry.startsWith(prefix));
  return cookie === undefined ? undefined : decodeURIComponent(cookie.slice(prefix.length));
}

/** Adds the CSRF token to requests that change state; reads go out unchanged. */
export function withCsrfToken(request: Request): Request {
  const token = readCookie(CSRF_COOKIE);
  if (!UNSAFE_METHODS.has(request.method) || token === undefined) {
    return request;
  }
  const headers = new Headers(request.headers);
  headers.set(CSRF_HEADER, token);
  return new Request(request, { headers });
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
