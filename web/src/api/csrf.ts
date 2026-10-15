// CSRF token handling (plan 6.2). No window access at load time: test helpers import it too.

/** Cookie where the Core API leaves the CSRF token, and header where it expects it back (plan 6.2). */
export const CSRF_COOKIE = 'XSRF-TOKEN';
export const CSRF_HEADER = 'X-XSRF-TOKEN';

const UNSAFE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

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
