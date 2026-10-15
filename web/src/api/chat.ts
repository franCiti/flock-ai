import { ApiError, api } from './client.ts';
import type { components } from './schema.ts';

export type Persona = components['schemas']['PersonaView'];
export type ClientConfig = components['schemas']['ClientConfig'];

/*
 * Messages of the conversation stream: the AgentReply of the contract, forwarded as is by the Core
 * API (contracts/schemas/agent-reply.v1.json). They are not in the OpenAPI spec (it only describes
 * the stream as text), so they are written here.
 */

interface ReplyEnvelope {
  version: number;
  requestId: string | null;
  conversationId: string | null;
  personaId: string | null;
  seq: number;
  sentAt: string;
}

export interface PersonaRef {
  id: string;
  displayName: string;
}

export interface Citation {
  documentId: string;
  title: string;
  url?: string | null;
  path?: string | null;
  section?: string | null;
  sourceType: string;
}

export type Outcome =
  | 'answered'
  | 'partially_answered'
  | 'no_information'
  | 'out_of_scope'
  | 'small_talk'
  | 'about_assistant';

export interface AcceptedReply extends ReplyEnvelope {
  type: 'accepted';
  deadlineAt: string;
}

export interface TokenReply extends ReplyEnvelope {
  type: 'token';
  text: string;
}

export interface FinalReply extends ReplyEnvelope {
  type: 'final';
  answer: string;
  outcome: Outcome;
  persona: PersonaRef;
  citations: Citation[];
  referral?: PersonaRef | null;
}

export interface ErrorReply extends ReplyEnvelope {
  type: 'error';
  code: string;
  message: string;
  retryable: boolean;
}

export type AgentReply = AcceptedReply | TokenReply | FinalReply | ErrorReply;

const REPLY_TYPES = ['accepted', 'token', 'final', 'error'] as const;

export async function fetchPersonas(): Promise<Persona[]> {
  const { data, response } = await api.GET('/api/personas');
  if (data === undefined) {
    throw new ApiError(response.status);
  }
  return data;
}

export async function fetchConfig(): Promise<ClientConfig> {
  const { data, response } = await api.GET('/api/config');
  if (data === undefined) {
    throw new ApiError(response.status);
  }
  return data;
}

/** Sends a question; its replies arrive through the stream of the conversation. */
export async function sendQuestion(
  conversationId: string,
  personaId: string,
  question: string,
): Promise<string> {
  const { data, response } = await api.POST('/api/conversations/{conversationId}/messages', {
    params: { path: { conversationId } },
    body: { personaId, question },
  });
  if (data?.requestId === undefined) {
    throw new ApiError(response.status);
  }
  return data.requestId;
}

export interface ReplyStream {
  close(): void;
}

/**
 * Opens the stream of a conversation (plan 6.4). The browser reconnects by itself and the Core API
 * replays what was missed; {@code onClosed} means it gave up (for example, the session ended).
 */
export function openReplyStream(
  conversationId: string,
  handlers: { onReply: (reply: AgentReply) => void; onClosed: () => void },
): ReplyStream {
  const source = new EventSource(`/api/conversations/${encodeURIComponent(conversationId)}/stream`);
  const listener = (event: MessageEvent<string>) => {
    handlers.onReply(JSON.parse(event.data) as AgentReply);
  };
  for (const type of REPLY_TYPES) {
    source.addEventListener(type, listener);
  }
  source.addEventListener('error', () => {
    if (source.readyState === EventSource.CLOSED) {
      handlers.onClosed();
    }
  });
  return {
    close: () => {
      source.close();
    },
  };
}
