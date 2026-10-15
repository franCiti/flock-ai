import { HttpResponse, http } from 'msw';
import { setupServer } from 'msw/node';
import type { AuditPage } from '../api/audit.ts';
import type { Credentials, CurrentUser } from '../api/auth.ts';
import type { Persona } from '../api/chat.ts';
import type { IngestionRun } from '../api/ingestion.ts';

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

export const testPersonas: Persona[] = [
  { id: 'juan-plataforma', displayName: 'Juan Pérez' },
  { id: 'ana-datos', displayName: 'Ana Gómez' },
];

/** A question the simulated Core API received. */
export interface SentQuestion {
  conversationId: string;
  personaId: string;
  question: string;
  requestId: string;
}

/** Personas, settings and the questions of the chat; each question gets request-1, request-2... */
export function mockChatApi(
  options: { personas?: Persona[]; maxQuestionChars?: number; sendStatus?: number } = {},
) {
  const questions: SentQuestion[] = [];
  server.use(
    http.get('*/api/personas', () => HttpResponse.json(options.personas ?? testPersonas)),
    http.get('*/api/config', () =>
      HttpResponse.json({ maxQuestionChars: options.maxQuestionChars ?? 2000 }),
    ),
    http.post('*/api/conversations/:conversationId/messages', async ({ request, params }) => {
      if (options.sendStatus !== undefined) {
        return new HttpResponse(null, { status: options.sendStatus });
      }
      const body = (await request.json()) as { personaId: string; question: string };
      const requestId = `request-${String(questions.length + 1)}`;
      questions.push({ conversationId: String(params.conversationId), ...body, requestId });
      return HttpResponse.json({ requestId }, { status: 202 });
    }),
  );
  return { questions };
}

/**
 * The knowledge updates: {@code history} is what GET answers (it can change between calls); a POST
 * adds a "requested" run at the top, or answers {@code requestStatus}.
 */
export function mockIngestionApi(options: {
  history: IngestionRun[] | (() => IngestionRun[]);
  requestStatus?: number;
}) {
  const requested: IngestionRun[] = [];
  server.use(
    http.get('*/api/ingestion/runs', () => {
      const history = typeof options.history === 'function' ? options.history() : options.history;
      return HttpResponse.json([...requested, ...history]);
    }),
    http.post('*/api/ingestion/runs', () => {
      if (options.requestStatus !== undefined) {
        return new HttpResponse(null, { status: options.requestStatus });
      }
      const jobId = `job-${String(requested.length + 1)}`;
      requested.unshift({
        jobId,
        trigger: 'manual',
        status: 'requested',
        requestedAt: '2026-10-15T15:00:00Z',
        personas: [],
        removedPersonas: [],
      });
      return HttpResponse.json({ jobId }, { status: 202 });
    }),
  );
  return { requested };
}

/** The audit log: answers {@code page} to every request and keeps the query of each one. */
export function mockAuditApi(page: AuditPage) {
  const queries: URLSearchParams[] = [];
  server.use(
    http.get('*/api/audit', ({ request }) => {
      queries.push(new URL(request.url).searchParams);
      return HttpResponse.json(page);
    }),
  );
  return { queries, lastQuery: () => queries.at(-1) ?? new URLSearchParams() };
}
