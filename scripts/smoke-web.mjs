// Smoke test of the web app (plan 8.5, stage 2): everything a browser does, against the nginx of
// the "web" service at http://localhost:8080 — pages and docs, login, a question to the agent with
// its streamed reply, a manual knowledge update, the audit log and logout.
//
// Called by scripts/smoke.sh once the stack is up and examples/knowledge is ingested. Uses the real
// LLM (D41). Credentials: ADMIN_USERNAME and ADMIN_PASSWORD of the repository .env.
//
//   node scripts/smoke-web.mjs

import { existsSync } from 'node:fs';
import { randomUUID } from 'node:crypto';

const BASE_URL = process.env.WEB_URL ?? 'http://localhost:8080';
const PERSONA = 'juan-plataforma';
const QUESTION = '¿Cómo hago rollback de un deploy?';
const EXPECTED_SOURCE = 'procedimientos/rollback.md';
const ANSWER_TIMEOUT_MS = 150_000;
const UPDATE_TIMEOUT_MS = 300_000;

const envFile = new URL('../.env', import.meta.url);
if (existsSync(envFile)) {
  process.loadEnvFile(envFile);
}

let failures = 0;
function check(description, ok, detail = '') {
  console.log(`  ${ok ? 'ok  ' : 'FAIL'}  ${description}${detail ? ` (${detail})` : ''}`);
  if (!ok) {
    failures += 1;
  }
  return ok;
}

function step(title) {
  console.log(`\n==> ${title}`);
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/** A minimal browser: keeps the cookies and sends the CSRF token back, like the web app. */
const cookies = new Map();
function cookieHeader() {
  return [...cookies].map(([name, value]) => `${name}=${value}`).join('; ');
}
async function request(method, path, body) {
  const headers = { Cookie: cookieHeader() };
  if (method !== 'GET' && cookies.has('XSRF-TOKEN')) {
    headers['X-XSRF-TOKEN'] = decodeURIComponent(cookies.get('XSRF-TOKEN'));
  }
  if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
  }
  const response = await fetch(new URL(path, BASE_URL), {
    method,
    headers,
    redirect: 'manual',
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  for (const cookie of response.headers.getSetCookie()) {
    const [pair] = cookie.split(';');
    const separator = pair.indexOf('=');
    const value = pair.slice(separator + 1);
    if (value) {
      cookies.set(pair.slice(0, separator), value);
    } else {
      cookies.delete(pair.slice(0, separator));
    }
  }
  return response;
}

/** Reads the SSE stream until a final or error reply; returns the replies by type. */
async function readReplies(stream, startedAt) {
  const reader = stream.body.getReader();
  const decoder = new TextDecoder();
  const replies = { accepted: null, tokens: 0, firstTokenMs: null, end: null };
  const deadline = Date.now() + ANSWER_TIMEOUT_MS;
  let buffer = '';
  while (Date.now() < deadline && replies.end === null) {
    const { value, done } = await Promise.race([
      reader.read(),
      sleep(deadline - Date.now()).then(() => ({ done: true })),
    ]);
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    let end;
    while ((end = buffer.indexOf('\n\n')) >= 0) {
      const block = buffer.slice(0, end);
      buffer = buffer.slice(end + 2);
      const type = /^event:(.*)$/m.exec(block)?.[1]?.trim();
      const data = /^data:(.*)$/m.exec(block)?.[1];
      if (type === 'accepted') {
        replies.accepted = JSON.parse(data);
      } else if (type === 'token') {
        replies.tokens += 1;
        replies.firstTokenMs ??= Date.now() - startedAt;
      } else if (type === 'final' || type === 'error') {
        replies.end = JSON.parse(data);
      }
    }
  }
  await reader.cancel().catch(() => undefined);
  return replies;
}

step(`Pages and documentation at ${BASE_URL}`);
const page = await fetch(new URL('/chat', BASE_URL));
check('the front answers on any route', page.ok && (await page.text()).includes('<div id="root">'));
check(
  'the front has its Content-Security-Policy',
  (page.headers.get('content-security-policy') ?? '').includes("default-src 'self'"),
);
for (const path of ['/docs/', '/docs/swagger-ui/index.html', '/docs/asyncapi/']) {
  const response = await fetch(new URL(path, BASE_URL));
  check(`${path} is public`, response.status === 200, `HTTP ${response.status}`);
}

step('Login');
const username = process.env.ADMIN_USERNAME ?? '';
const password = process.env.ADMIN_PASSWORD ?? '';
if (!check('ADMIN_USERNAME and ADMIN_PASSWORD are set in .env', username !== '' && password !== '')) {
  process.exit(1);
}
check('without a session the API answers 401', (await request('GET', '/api/auth/me')).status === 401);
const login = await request('POST', '/api/auth/login', { username, password });
if (!check('login', login.status === 204, `HTTP ${login.status}`)) {
  process.exit(1);
}
const me = await request('GET', '/api/auth/me');
check('the session is open', me.status === 200 && (await me.json()).username === username);

const personas = await (await request('GET', '/api/personas')).json();
check(`the personas include ${PERSONA}`, personas.some((persona) => persona.id === PERSONA));
const config = await (await request('GET', '/api/config')).json();
check('the config has maxQuestionChars', Number.isInteger(config.maxQuestionChars));

step(`Asking ${PERSONA}: ${QUESTION}`);
const conversationId = randomUUID();
const stream = await fetch(new URL(`/api/conversations/${conversationId}/stream`, BASE_URL), {
  headers: { Cookie: cookieHeader(), Accept: 'text/event-stream' },
});
check('the stream opens', stream.status === 200, `HTTP ${stream.status}`);
const startedAt = Date.now();
const sent = await request('POST', `/api/conversations/${conversationId}/messages`, {
  personaId: PERSONA,
  question: QUESTION,
});
check('the question is accepted', sent.status === 202, `HTTP ${sent.status}`);
const { requestId } = await sent.json();
const replies = await readReplies(stream, startedAt);
const answer = replies.end;
check('an accepted reply with its deadline arrives', replies.accepted?.deadlineAt !== undefined);
check(
  'the answer streams in tokens',
  replies.tokens > 0,
  `${replies.tokens} tokens, first after ${((replies.firstTokenMs ?? 0) / 1000).toFixed(1)} s`,
);
check(
  'a final reply arrives',
  answer?.type === 'final',
  answer?.type === 'error' ? `${answer.code}: ${answer.message}` : `${((Date.now() - startedAt) / 1000).toFixed(1)} s`,
);
check('the outcome is answered', answer?.outcome === 'answered', answer?.outcome);
check(
  `it cites ${EXPECTED_SOURCE}`,
  (answer?.citations ?? []).some((citation) => citation.path === EXPECTED_SOURCE),
);
if (answer?.type === 'final') {
  console.log(`\n${answer.answer}\n`);
}

step('Updating the knowledge from the web');
const update = await request('POST', '/api/ingestion/runs');
check('the update is requested', update.status === 202, `HTTP ${update.status}`);
const { jobId } = await update.json();
let run;
const updateDeadline = Date.now() + UPDATE_TIMEOUT_MS;
while (Date.now() < updateDeadline) {
  await sleep(3_000);
  const history = await (await request('GET', '/api/ingestion/runs?limit=5')).json();
  run = history.find((entry) => entry.jobId === jobId);
  if (['completed', 'failed', 'rejected'].includes(run?.status)) {
    break;
  }
}
check('the update completes', run?.status === 'completed', run?.reason ?? run?.status);
check('it covers both example personas', run?.totals?.personas === 2, `${run?.totals?.personas}`);

step('Audit log');
let entry;
for (let attempt = 0; attempt < 15 && entry === undefined; attempt += 1) {
  const audit = await (await request('GET', `/api/audit?personaId=${PERSONA}&size=20`)).json();
  entry = audit.items.find((item) => item.requestId === requestId);
  if (entry === undefined) {
    await sleep(2_000);
  }
}
check('the question is in the audit log', entry !== undefined);
check('with its outcome and sources', entry?.outcome === 'answered' && entry.citations.length > 0);

step('Logout');
check('logout', (await request('POST', '/api/auth/logout')).status === 204);
check('the session is closed', (await request('GET', '/api/auth/me')).status === 401);

if (failures > 0) {
  console.log(`\nWeb smoke test FAILED (${failures} checks)`);
  process.exit(1);
}
console.log('\nWeb smoke test passed');
