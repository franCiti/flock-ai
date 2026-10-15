import type {
  AcceptedReply,
  Citation,
  ErrorReply,
  FinalReply,
  PersonaRef,
  TokenReply,
} from '../api/chat.ts';

/** Replies of the agent as the contract defines them (contracts/examples/agent-reply). */

const SENT_AT = '2026-10-15T12:00:00.000Z';

function envelope(requestId: string, seq: number) {
  return {
    version: 1,
    requestId,
    conversationId: 'conversation',
    personaId: 'juan-plataforma',
    seq,
    sentAt: SENT_AT,
  };
}

/** The agent has {@code seconds} to answer, measured on the server clock. */
export function accepted(requestId: string, seconds = 120): AcceptedReply {
  const deadlineAt = new Date(Date.parse(SENT_AT) + seconds * 1000).toISOString();
  return { ...envelope(requestId, 0), type: 'accepted', deadlineAt };
}

export function token(requestId: string, seq: number, text: string): TokenReply {
  return { ...envelope(requestId, seq), type: 'token', text };
}

export function final(
  requestId: string,
  seq: number,
  answer: string,
  extra: { citations?: Citation[]; referral?: PersonaRef } = {},
): FinalReply {
  return {
    ...envelope(requestId, seq),
    type: 'final',
    answer,
    outcome: 'answered',
    persona: { id: 'juan-plataforma', displayName: 'Juan Pérez' },
    citations: extra.citations ?? [],
    referral: extra.referral ?? null,
  };
}

export function error(requestId: string, seq: number, retryable: boolean): ErrorReply {
  return {
    ...envelope(requestId, seq),
    type: 'error',
    code: retryable ? 'TIMEOUT' : 'QUESTION_TOO_LONG',
    message: retryable
      ? 'La respuesta tardó demasiado. Probá de nuevo en unos minutos.'
      : 'La pregunta es demasiado larga.',
    retryable,
  };
}
