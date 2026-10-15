import { CSRF_COOKIE, CSRF_HEADER, withCsrfToken } from './csrf.ts';

function setCsrfCookie(value: string | null) {
  document.cookie =
    value === null
      ? `${CSRF_COOKIE}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/`
      : `${CSRF_COOKIE}=${encodeURIComponent(value)}; path=/`;
}

describe('withCsrfToken', () => {
  afterEach(() => {
    setCsrfCookie(null);
  });

  it.each(['POST', 'PUT', 'PATCH', 'DELETE'])('adds the token to %s requests', (method) => {
    setCsrfCookie('token+1');

    const request = withCsrfToken(new Request('http://localhost/api/x', { method }));

    expect(request.headers.get(CSRF_HEADER)).toBe('token+1');
  });

  it('leaves reads unchanged', () => {
    setCsrfCookie('token');

    const request = withCsrfToken(new Request('http://localhost/api/x'));

    expect(request.headers.has(CSRF_HEADER)).toBe(false);
  });

  it('sends no header when there is no token yet', () => {
    const request = withCsrfToken(new Request('http://localhost/api/x', { method: 'POST' }));

    expect(request.headers.has(CSRF_HEADER)).toBe(false);
  });
});
